"""Small, cached GitHub contribution integration for admin performance."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dashboard.db_access import get_cursor


DEFAULT_REPOSITORY = "fajarsembar01/sudin_aska"
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_JAKARTA_TZ = timezone(timedelta(hours=7))
_CODE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".sql",
    ".sh", ".bash", ".zsh", ".ps1", ".vue", ".svelte", ".go",
    ".java", ".kt", ".kts", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".php", ".rb", ".rs", ".swift", ".xml", ".yml", ".yaml",
    ".toml", ".ini", ".cfg",
}
_CODE_FILENAMES = {"dockerfile", "makefile", "procfile", "requirements.txt"}


def normalize_repository(value: str) -> str:
    repository = (value or "").strip().strip("/")
    if repository.startswith("git@github.com:"):
        repository = repository[len("git@github.com:") :]
    if repository.startswith("https://github.com/"):
        repository = repository[len("https://github.com/") :].strip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not _REPOSITORY_RE.fullmatch(repository):
        raise ValueError("Repository harus memakai format owner/nama-repository.")
    return repository


def normalize_username(value: str) -> str:
    username = (value or "").strip().lstrip("@")
    if not username:
        return ""
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError(f"Username GitHub tidak valid: {value}")
    return username.lower()


def normalize_author_email(value: str) -> str:
    emails = []
    for raw_email in re.split(r"[,;\n]+", value or ""):
        email = raw_email.strip().lower()
        if not email:
            continue
        if len(email) > 254 or "@" not in email or any(char.isspace() for char in email):
            raise ValueError(f"Email author Git tidak valid: {raw_email.strip()}")
        if email not in emails:
            emails.append(email)
    return ",".join(emails)


def period_key(start: Optional[datetime], end: Optional[datetime]) -> str:
    if start and end:
        return f"{start.date().isoformat()}_{end.date().isoformat()}"
    return "all"


def list_admin_github_accounts() -> list[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, email, github_username, github_author_email, account_status
            FROM dashboard_users
            WHERE role = 'admin'
              AND COALESCE(account_status, 'approved') = 'approved'
            ORDER BY full_name ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def save_admin_github_accounts(entries: Iterable[Dict[str, Any]]) -> int:
    normalized = []
    for entry in entries:
        normalized.append((
            normalize_username(str(entry.get("github_username") or "")),
            normalize_author_email(str(entry.get("github_author_email") or "")),
            int(entry["id"]),
        ))
    usernames = [username for username, _email, _admin_id in normalized if username]
    if len(usernames) != len(set(usernames)):
        raise ValueError("Satu username GitHub hanya boleh dipasangkan ke satu admin.")
    author_emails = [
        email
        for _username, email_list, _admin_id in normalized
        for email in email_list.split(",")
        if email
    ]
    if len(author_emails) != len(set(author_emails)):
        raise ValueError("Satu email author Git hanya boleh dipasangkan ke satu admin.")
    with get_cursor(commit=True) as cur:
        for username, author_email, admin_id in normalized:
            cur.execute(
                """
                UPDATE dashboard_users
                SET github_username = NULLIF(%s, ''),
                    github_author_email = NULLIF(%s, '')
                WHERE id = %s AND role = 'admin'
                """,
                (username, author_email, admin_id),
            )
    return sum(1 for username, _email, _admin_id in normalized if username)


def _request_commit_page(
    repository: str,
    username: str,
    *,
    since: Optional[datetime],
    page: int,
    author_identity: Optional[str] = None,
    timeout: int = 12,
) -> list[Dict[str, Any]]:
    repository = normalize_repository(repository)
    username = normalize_username(username)
    params: Dict[str, Any] = {
        "author": author_identity or username,
        "per_page": 100,
        "page": page,
    }
    if since:
        local_start = (
            since.replace(tzinfo=_JAKARTA_TZ)
            if since.tzinfo is None
            else since.astimezone(_JAKARTA_TZ)
        )
        params["since"] = local_start.isoformat()
    request = Request(
        f"https://api.github.com/repos/{repository}/commits?{urlencode(params)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ASKA-Admin-Performance",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 409:
            return []
        if exc.code == 404:
            raise RuntimeError("Repository tidak ditemukan atau token tidak memiliki akses.") from exc
        if exc.code in {401, 403}:
            raise RuntimeError("Akses GitHub ditolak atau batas API tercapai. Periksa GITHUB_TOKEN.") from exc
        raise RuntimeError(f"GitHub API gagal dengan status {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("GitHub tidak dapat dihubungi. Coba sinkronkan kembali.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Respons GitHub tidak sesuai format yang diharapkan.")
    return payload


def fetch_commit_batches(
    repository: str,
    username: str,
    *,
    since: Optional[datetime],
    author_identity: Optional[str] = None,
    timeout: int = 12,
):
    """Yield at most 100 normalized commits at a time."""
    for page in range(1, 1001):
        payload = _request_commit_page(
            repository, username, since=since, page=page,
            author_identity=author_identity, timeout=timeout
        )
        rows = []
        for item in payload:
            commit = item.get("commit") or {}
            author = commit.get("author") or commit.get("committer") or {}
            if not item.get("sha") or not author.get("date"):
                continue
            rows.append(
                {
                    "sha": item["sha"],
                    "committed_at": author["date"],
                    "commit_url": item.get("html_url"),
                    "commit_message": commit.get("message"),
                }
            )
        if rows:
            yield rows
        if len(payload) < 100:
            return
    raise RuntimeError("Riwayat GitHub terlalu besar untuk satu proses sinkronisasi.")


def _save_commit_batch(repository: str, username: str, rows: list[Dict[str, Any]]) -> int:
    with get_cursor(commit=True) as cur:
        cur.executemany(
            """
            INSERT INTO github_admin_commits
                (repository, github_username, commit_sha, committed_at,
                 commit_url, commit_message, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (repository, github_username, commit_sha) DO NOTHING
            """,
            [
                (
                    repository, username, row["sha"], row["committed_at"],
                    row.get("commit_url"), row.get("commit_message"),
                )
                for row in rows
            ],
        )
        return max(0, int(cur.rowcount or 0))


def get_last_sync(
    repository: str, username: str, author_email: str = ""
) -> Optional[datetime]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT last_synced_at
            FROM github_admin_sync_state
            WHERE repository = %s AND LOWER(github_username) = LOWER(%s)
              AND COALESCE(LOWER(author_email), '') = %s
            """,
            (repository, username, author_email),
        )
        row = cur.fetchone()
    return row["last_synced_at"] if row else None


def _save_sync_state(
    repository: str, username: str, *, synced_by: int,
    synced_at: Optional[datetime], error: Optional[str], author_email: str = "",
) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO github_admin_sync_state
                (repository, github_username, author_email, last_synced_at, last_error, synced_by)
            VALUES (%s, %s, NULLIF(%s, ''), %s, %s, %s)
            ON CONFLICT (repository, github_username) DO UPDATE
            SET author_email = EXCLUDED.author_email,
                last_synced_at = COALESCE(EXCLUDED.last_synced_at, github_admin_sync_state.last_synced_at),
                last_error = EXCLUDED.last_error,
                synced_by = EXCLUDED.synced_by
            """,
            (repository, username, author_email, synced_at, error, synced_by),
        )


def sync_admin_commits(
    repository: str, username: str, *, synced_by: int, author_email: str = ""
) -> Dict[str, Any]:
    """Import all history once, then only commits since the last successful sync."""
    repository = normalize_repository(repository)
    username = normalize_username(username)
    author_email = normalize_author_email(author_email)
    last_sync = get_last_sync(repository, username, author_email)
    sync_checkpoint = datetime.now(timezone.utc)
    inserted = 0
    try:
        identities = [
            username,
            *[email for email in author_email.split(",") if email],
        ]
        for identity in identities:
            for batch in fetch_commit_batches(
                repository, username, since=last_sync,
                author_identity=identity,
            ):
                inserted += _save_commit_batch(repository, username, batch)
    except (RuntimeError, ValueError) as exc:
        _save_sync_state(
            repository, username, synced_by=synced_by,
            synced_at=None, error=str(exc), author_email=author_email,
        )
        raise
    _save_sync_state(
        repository, username, synced_by=synced_by,
        synced_at=sync_checkpoint, error=None, author_email=author_email,
    )
    return {"inserted": inserted, "initial": last_sync is None, "synced_at": sync_checkpoint}


def get_commit_snapshots(repository: str, key: str) -> Dict[int, Dict[str, Any]]:
    start = None
    exclusive_end = None
    if key != "all":
        start_text, end_text = key.split("_", 1)
        start = datetime.strptime(start_text, "%Y-%m-%d")
        exclusive_end = datetime.strptime(end_text, "%Y-%m-%d") + timedelta(days=1)
    date_clause = ""
    params: list[Any] = [repository]
    if start and exclusive_end:
        date_clause = "AND committed_at >= %s AND committed_at < %s"
        params.extend([start, exclusive_end])
    params.append(repository)
    with get_cursor() as cur:
        cur.execute(
            f"""
            WITH daily_commits AS (
                SELECT
                    LOWER(github_username) AS username_key,
                    (committed_at AT TIME ZONE 'Asia/Jakarta')::date AS commit_day,
                    COUNT(DISTINCT id)::INTEGER AS daily_count,
                    MAX(committed_at) AS daily_last_commit_at
                FROM github_admin_commits
                WHERE repository = %s
                  {date_clause}
                GROUP BY LOWER(github_username), (committed_at AT TIME ZONE 'Asia/Jakarta')::date
            ), commit_totals AS (
                SELECT
                    username_key,
                    SUM(daily_count)::INTEGER AS commit_count,
                    COUNT(*)::INTEGER AS coding_day_count,
                    MAX(daily_last_commit_at) AS last_commit_at
                FROM daily_commits
                GROUP BY username_key
            )
            SELECT
                u.id AS dashboard_user_id,
                u.github_username,
                CASE WHEN s.last_synced_at IS NULL THEN NULL ELSE COALESCE(t.commit_count, 0) END AS commit_count,
                CASE WHEN s.last_synced_at IS NULL THEN NULL ELSE COALESCE(t.coding_day_count, 0) END AS coding_day_count,
                t.last_commit_at,
                s.last_error AS sync_error,
                s.last_synced_at AS synced_at
            FROM dashboard_users u
            LEFT JOIN commit_totals t
              ON t.username_key = LOWER(u.github_username)
            LEFT JOIN github_admin_sync_state s
              ON s.repository = %s
             AND LOWER(s.github_username) = LOWER(u.github_username)
            WHERE u.role = 'admin'
            """,
            tuple(params),
        )
        return {int(row["dashboard_user_id"]): dict(row) for row in cur.fetchall()}


def get_commit_daily_series(
    repository: str, key: str, *, admin_id: Optional[int] = None
) -> list[Dict[str, Any]]:
    start = None
    exclusive_end = None
    if key != "all":
        start_text, end_text = key.split("_", 1)
        start = datetime.strptime(start_text, "%Y-%m-%d")
        exclusive_end = datetime.strptime(end_text, "%Y-%m-%d") + timedelta(days=1)
    conditions = ["c.repository = %s", "u.role = 'admin'"]
    params: list[Any] = [repository]
    if start and exclusive_end:
        conditions.extend(["c.committed_at >= %s", "c.committed_at < %s"])
        params.extend([start, exclusive_end])
    if admin_id:
        conditions.append("u.id = %s")
        params.append(int(admin_id))
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT c.committed_at::date AS activity_day, COUNT(DISTINCT c.id)::INTEGER AS count
            FROM github_admin_commits c
            JOIN dashboard_users u
              ON LOWER(u.github_username) = LOWER(c.github_username)
            WHERE {' AND '.join(conditions)}
            GROUP BY c.committed_at::date
            ORDER BY c.committed_at::date
            """,
            tuple(params),
        )
        return [
            {"day": row["activity_day"].isoformat(), "count": int(row["count"] or 0)}
            for row in cur.fetchall()
        ]


def _commit_period_conditions(
    repository: str, username: str, start: Optional[datetime], end: Optional[datetime]
) -> tuple[list[str], list[Any]]:
    conditions = ["repository = %s", "LOWER(github_username) = LOWER(%s)"]
    params: list[Any] = [repository, username]
    if start:
        conditions.append("committed_at >= %s")
        params.append(start)
    if end:
        conditions.append("committed_at < %s")
        params.append(end + timedelta(days=1))
    return conditions, params


def _is_code_path(value: str) -> bool:
    path = (value or "").strip().lower()
    if not path or path.startswith(("node_modules/", "uploads/", "runtime/")):
        return False
    filename = path.rsplit("/", 1)[-1]
    return filename in _CODE_FILENAMES or Path(filename).suffix in _CODE_EXTENSIONS


def hydrate_commit_line_stats(
    repository: str,
    username: str,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
) -> Dict[str, int]:
    """Fill missing numstat values from the local repository in bounded batches."""
    repository = normalize_repository(repository)
    username = normalize_username(username)
    repo_root = Path(__file__).resolve().parents[2]
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=repo_root,
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if normalize_repository(remote) != repository:
            return {"updated": 0}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"updated": 0}

    conditions, params = _commit_period_conditions(repository, username, start, end)
    conditions.append("stats_synced_at IS NULL")
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT commit_sha
            FROM github_admin_commits
            WHERE {' AND '.join(conditions)}
            ORDER BY committed_at ASC
            LIMIT 2000
            """,
            tuple(params),
        )
        shas = [str(row["commit_sha"]) for row in cur.fetchall()]

    parsed: Dict[str, Dict[str, int]] = {}
    for offset in range(0, len(shas), 80):
        chunk = shas[offset : offset + 80]
        try:
            result = subprocess.run(
                [
                    "git", "show", "--first-parent", "--numstat",
                    "--format=__COMMIT__%H", "--no-renames", "--no-ext-diff",
                    *chunk,
                ],
                cwd=repo_root, check=True, capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        current_sha = None
        for line in result.stdout.splitlines():
            if line.startswith("__COMMIT__"):
                current_sha = line[len("__COMMIT__") :].strip()
                parsed[current_sha] = {"additions": 0, "deletions": 0}
                continue
            if not current_sha or "\t" not in line:
                continue
            added, deleted, changed_path = (line.split("\t", 2) + [""])[:3]
            if not _is_code_path(changed_path):
                continue
            if added.isdigit():
                parsed[current_sha]["additions"] += int(added)
            if deleted.isdigit():
                parsed[current_sha]["deletions"] += int(deleted)

    if parsed:
        with get_cursor(commit=True) as cur:
            cur.executemany(
                """
                UPDATE github_admin_commits
                SET additions = %s, deletions = %s, stats_synced_at = NOW()
                WHERE repository = %s
                  AND LOWER(github_username) = LOWER(%s)
                  AND commit_sha = %s
                """,
                [
                    (values["additions"], values["deletions"], repository, username, sha)
                    for sha, values in parsed.items()
                ],
            )
    return {"updated": len(parsed)}


def get_commit_line_summary(
    repository: str,
    username: str,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
) -> Dict[str, int]:
    conditions, params = _commit_period_conditions(repository, username, start, end)
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                COUNT(*)::INTEGER AS total_commits,
                COUNT(additions)::INTEGER AS measured_commits,
                COALESCE(SUM(additions), 0)::BIGINT AS additions,
                COALESCE(SUM(deletions), 0)::BIGINT AS deletions
            FROM github_admin_commits
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        )
        row = dict(cur.fetchone() or {})
    additions = int(row.get("additions") or 0)
    deletions = int(row.get("deletions") or 0)
    total_commits = int(row.get("total_commits") or 0)
    measured = int(row.get("measured_commits") or 0)
    return {
        "additions": additions,
        "deletions": deletions,
        "changed_lines": additions + deletions,
        "measured_commits": measured,
        "total_commits": total_commits,
        "missing_commits": max(0, total_commits - measured),
    }


def get_commit_line_totals(
    repository: str, key: str, *, admin_id: Optional[int] = None
) -> Dict[str, int]:
    """Return cached code-line totals for the selected period and admin scope."""
    repository = normalize_repository(repository)
    conditions = ["c.repository = %s", "u.role = 'admin'"]
    params: list[Any] = [repository]
    if key != "all":
        start_text, end_text = key.split("_", 1)
        start = datetime.strptime(start_text, "%Y-%m-%d")
        exclusive_end = datetime.strptime(end_text, "%Y-%m-%d") + timedelta(days=1)
        conditions.extend(["c.committed_at >= %s", "c.committed_at < %s"])
        params.extend([start, exclusive_end])
    if admin_id:
        conditions.append("u.id = %s")
        params.append(int(admin_id))
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                COUNT(*)::INTEGER AS total_commits,
                COUNT(c.additions)::INTEGER AS measured_commits,
                COALESCE(SUM(c.additions), 0)::BIGINT AS additions,
                COALESCE(SUM(c.deletions), 0)::BIGINT AS deletions
            FROM github_admin_commits c
            JOIN dashboard_users u
              ON LOWER(u.github_username) = LOWER(c.github_username)
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        )
        row = dict(cur.fetchone() or {})
    additions = int(row.get("additions") or 0)
    deletions = int(row.get("deletions") or 0)
    total_commits = int(row.get("total_commits") or 0)
    measured = int(row.get("measured_commits") or 0)
    return {
        "additions": additions,
        "deletions": deletions,
        "changed_lines": additions + deletions,
        "measured_commits": measured,
        "total_commits": total_commits,
        "missing_commits": max(0, total_commits - measured),
    }


def attach_github_metrics(rows: Iterable[Dict[str, Any]], snapshots: Dict[int, Dict[str, Any]]) -> None:
    for row in rows:
        snapshot = snapshots.get(int(row.get("actor_user_id") or 0), {})
        row["github_username"] = snapshot.get("github_username")
        row["github_commits"] = snapshot.get("commit_count")
        row["github_coding_days"] = snapshot.get("coding_day_count")
        row["github_all_time_commits"] = snapshot.get("all_time_commit_count")
        row["github_last_commit_at"] = snapshot.get("all_time_last_commit_at")
        row["github_sync_error"] = snapshot.get("sync_error")
        row["github_synced_at"] = snapshot.get("synced_at")
