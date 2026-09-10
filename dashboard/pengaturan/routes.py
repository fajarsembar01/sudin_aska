from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from dashboard.auth import current_user, role_required
from dashboard.portal import routes as portal_routes
from dashboard.queries import (
    fetch_admin_activity_events,
    fetch_admin_activity_page,
    fetch_admin_performance_data,
    list_admin_users,
    fetch_telegram_notification_settings,
    upsert_telegram_notification_settings,
    list_telegram_admin_accounts,
    upsert_telegram_admin_accounts,
    delete_telegram_admin_account,
    list_telegram_notification_groups,
    delete_telegram_notification_group,
)
from dashboard.telegram_notifications import send_test_notification
from utils import current_jakarta_time
from .admin_performance_pdf import build_admin_performance_pdf
from .github_performance import (
    DEFAULT_REPOSITORY,
    attach_github_metrics,
    get_commit_daily_series,
    get_commit_line_summary,
    get_commit_line_totals,
    get_commit_snapshots,
    hydrate_commit_line_stats,
    list_admin_github_accounts,
    normalize_repository,
    period_key,
    save_admin_github_accounts,
    sync_admin_commits,
)
from .queries import (
    get_all_system_settings,
    get_system_setting,
    update_system_settings,
    get_system_diagnostic_info,
    list_public_api_keys,
    create_public_api_key,
    toggle_public_api_key_status,
    delete_public_api_key,
    verify_public_api_key,
    fetch_public_schools_api_data,
)

pengaturan_bp = Blueprint(
    "pengaturan",
    __name__,
    url_prefix="/dashboard/pengaturan",
    template_folder="templates",
)
pengaturan_legacy_bp = Blueprint(
    "pengaturan_legacy",
    __name__,
    url_prefix="/pengaturan",
)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _resolve_admin_performance_period() -> Dict[str, Any]:
    period_scope = (request.values.get("period_scope") or "month").strip().lower()
    if period_scope not in {"month", "year", "all"}:
        period_scope = "month"

    now = current_jakarta_time()
    selected_month = (request.values.get("month") or now.strftime("%Y-%m")).strip()
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = now.strftime("%Y-%m")
        month_start = datetime(now.year, now.month, 1)

    selected_year = request.values.get("year", type=int) or now.year
    if selected_year < 2000 or selected_year > now.year:
        selected_year = now.year

    if period_scope == "month":
        start = month_start
        if month_start.month == 12:
            next_month = datetime(month_start.year + 1, 1, 1)
        else:
            next_month = datetime(month_start.year, month_start.month + 1, 1)
        end = next_month - timedelta(days=1)
    elif period_scope == "year":
        start = datetime(selected_year, 1, 1)
        end = datetime(selected_year, 12, 31)
    else:
        start = None
        end = None

    return {
        "period_scope": period_scope,
        "selected_month": selected_month,
        "selected_year": selected_year,
        "year_options": list(range(now.year, 1999, -1)),
        "start": start,
        "end": end,
        "generated_at": now,
    }


def _complete_admin_leaderboard(
    leaderboard: list[Dict[str, Any]], admin_users: list[Dict[str, Any]],
    *, minimum_actions: int = 0,
) -> list[Dict[str, Any]]:
    """Return current admins, including accounts without matching activity."""
    active_admin_ids = {
        int(admin.get("id") or 0) for admin in admin_users if admin.get("id")
    }
    rows_by_id = {
        int(row["actor_user_id"]): dict(row)
        for row in leaderboard
        if row.get("actor_user_id")
        and int(row["actor_user_id"]) in active_admin_ids
    }
    for admin in admin_users:
        admin_id = int(admin.get("id") or 0)
        if not admin_id:
            continue
        row = rows_by_id.setdefault(
            admin_id,
            {
                "actor_user_id": admin_id,
                "total_actions": 0,
                "last_action_at": None,
                "feature_counts": {},
                "action_counts": {},
            },
        )
        row["actor_name"] = admin.get("full_name") or row.get("actor_name")
        row["actor_email"] = admin.get("email") or row.get("actor_email")
        row["actor_label"] = (
            admin.get("full_name")
            or admin.get("email")
            or row.get("actor_label")
            or f"Admin #{admin_id}"
        )

    rows = [
        row
        for row in rows_by_id.values()
        if int(row.get("total_actions") or 0) >= minimum_actions
    ]
    rows.sort(
        key=lambda row: (
            -int(row.get("total_actions") or 0),
            (row.get("actor_label") or "").lower(),
        )
    )
    return rows


def _score_admin_leaderboard(
    leaderboard: list[Dict[str, Any]], *, coding_multiplier: int = 10
) -> list[Dict[str, Any]]:
    scored = []
    for source in leaderboard:
        row = dict(source)
        actions = int(row.get("total_actions") or 0)
        scored_value = row.get("github_coding_days")
        coding_updates = int(
            scored_value if scored_value is not None else row.get("github_commits") or 0
        )
        row["coding_score_units"] = coding_updates
        row["coding_points"] = coding_updates * coding_multiplier
        row["performance_total"] = actions + row["coding_points"]
        row["coding_multiplier"] = coding_multiplier
        scored.append(row)
    scored.sort(
        key=lambda row: (
            -int(row["performance_total"]),
            -int(row.get("total_actions") or 0),
            (row.get("actor_label") or "").lower(),
        )
    )
    return scored


def _admin_performance_period_label(period: Dict[str, Any]) -> str:
    month_names = (
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    )
    if period["period_scope"] == "month" and period.get("start"):
        start = period["start"]
        return f"{month_names[start.month - 1]} {start.year}"
    if period["period_scope"] == "year":
        return f"Tahun {period['selected_year']}"
    return "Seluruh riwayat"


def _github_performance_context(period: Dict[str, Any]) -> Dict[str, Any]:
    repository = normalize_repository(
        get_system_setting("github_performance_repository", DEFAULT_REPOSITORY)
        or DEFAULT_REPOSITORY
    )
    key = period_key(period["start"], period["end"])
    snapshots = get_commit_snapshots(repository, key)
    all_time_snapshots = snapshots if key == "all" else get_commit_snapshots(repository, "all")
    accounts = list_admin_github_accounts()
    for account in accounts:
        admin_id = int(account["id"])
        snapshot = dict(snapshots.get(admin_id, {}))
        snapshot["github_username"] = account.get("github_username")
        snapshot.setdefault("commit_count", None)
        snapshot.setdefault("coding_day_count", None)
        snapshot.setdefault("sync_error", None)
        snapshot.setdefault("synced_at", None)
        all_time = all_time_snapshots.get(admin_id, {})
        snapshot["all_time_commit_count"] = all_time.get("commit_count")
        snapshot["all_time_last_commit_at"] = all_time.get("last_commit_at")
        snapshots[admin_id] = snapshot
        account.update(snapshot)
    return {
        "repository": repository,
        "period_key": key,
        "snapshots": snapshots,
        "all_time_snapshots": all_time_snapshots,
        "accounts": accounts,
        "last_synced_at": max(
            (item.get("synced_at") for item in snapshots.values() if item.get("synced_at")),
            default=None,
        ),
    }


def _performance_redirect_from_form() -> Response:
    allowed = ("feature", "admin_id", "action", "target_type", "search", "period_scope", "month", "year")
    values = {key: request.form.get(key) for key in allowed if request.form.get(key)}
    return redirect(url_for("pengaturan.admin_performance", **values))


@pengaturan_bp.route("/admin-performance")
@role_required("admin")
def admin_performance() -> Response:
    feature_key = (request.args.get("feature") or "all").strip().lower() or "all"
    admin_id = request.args.get("admin_id", type=int)
    action = (request.args.get("action") or "").strip().upper() or None
    target_type = (request.args.get("target_type") or "").strip().upper() or None
    search = (request.args.get("search") or "").strip() or None
    period = _resolve_admin_performance_period()

    data = fetch_admin_performance_data(
        feature_key=feature_key,
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        search=search,
        start=period["start"],
        end=period["end"],
        detail_limit=400,
    )
    github = _github_performance_context(period)
    leaderboard_accounts = github["accounts"]
    if admin_id:
        leaderboard_accounts = [
            account for account in leaderboard_accounts
            if int(account.get("id") or 0) == admin_id
        ]
    leaderboard = _complete_admin_leaderboard(
        data.get("leaderboard") or [], leaderboard_accounts, minimum_actions=0
    )
    attach_github_metrics(leaderboard, github["snapshots"])
    data["leaderboard"] = _score_admin_leaderboard(leaderboard)
    selected_snapshots = github["snapshots"]
    if admin_id:
        selected_snapshots = {
            admin_id: github["snapshots"][admin_id]
        } if admin_id in github["snapshots"] else {}
    github_counts = [
        int(item["commit_count"])
        for item in selected_snapshots.values()
        if item.get("commit_count") is not None
    ]
    github_coding_days = [
        int(item["coding_day_count"])
        for item in selected_snapshots.values()
        if item.get("coding_day_count") is not None
    ]
    github_all_time_counts = [
        int(item["all_time_commit_count"])
        for item in selected_snapshots.values()
        if item.get("all_time_commit_count") is not None
    ]
    github_daily_series = get_commit_daily_series(
        github["repository"], github["period_key"], admin_id=admin_id
    )
    github_line_totals = get_commit_line_totals(
        github["repository"], github["period_key"], admin_id=admin_id
    )
    data.update(
        {
            "period_scope": period["period_scope"],
            "selected_month": period["selected_month"],
            "selected_year": period["selected_year"],
            "year_options": period["year_options"],
            "github": github,
            "github_total_commits": sum(github_counts),
            "github_coding_days": sum(github_coding_days),
            "github_all_time_commits": sum(github_all_time_counts),
            "github_contributors": sum(1 for count in github_counts if count > 0),
            "github_daily_series": github_daily_series,
            "github_line_totals": github_line_totals,
            "period_label": _admin_performance_period_label(period),
            "total_performance_score": sum(
                int(item.get("performance_total") or 0)
                for item in data["leaderboard"]
            ),
            "top_performance_score": (
                int(data["leaderboard"][0].get("performance_total") or 0)
                if data["leaderboard"] else 0
            ),
        }
    )
    return render_template("admin_performance.html", performance=data)


@pengaturan_bp.route("/admin-performance/github-settings", methods=["POST"])
@role_required("admin")
def admin_performance_github_settings() -> Response:
    try:
        repository = normalize_repository(request.form.get("github_repository") or "")
        admins = list_admin_github_accounts()
        entries = [
            {
                "id": admin["id"],
                "github_username": request.form.get(f"github_username_{admin['id']}", ""),
                "github_author_email": request.form.get(f"github_author_email_{admin['id']}", ""),
            }
            for admin in admins
        ]
        mapped = save_admin_github_accounts(entries)
        update_system_settings(
            {"github_performance_repository": repository},
            user_id=(current_user() or {}).get("id"),
        )
        flash(f"Pengaturan GitHub disimpan. {mapped} akun admin telah dipetakan.", "success")
    except (KeyError, TypeError, ValueError) as exc:
        flash(str(exc), "danger")
    return _performance_redirect_from_form()


@pengaturan_bp.route("/admin-performance/github-sync", methods=["POST"])
@role_required("admin")
def admin_performance_github_sync() -> Response:
    try:
        repository = normalize_repository(
            get_system_setting("github_performance_repository", DEFAULT_REPOSITORY)
            or DEFAULT_REPOSITORY
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return _performance_redirect_from_form()
    actor_id = int((current_user() or {}).get("id") or 0)
    accounts = [item for item in list_admin_github_accounts() if item.get("github_username")]
    success_count = 0
    inserted_count = 0
    initial_count = 0
    errors = []
    for account in accounts:
        try:
            result = sync_admin_commits(
                repository, account["github_username"], synced_by=actor_id,
                author_email=account.get("github_author_email") or "",
            )
            hydrate_commit_line_stats(
                repository, account["github_username"], start=None, end=None
            )
            success_count += 1
            inserted_count += int(result.get("inserted") or 0)
            initial_count += 1 if result.get("initial") else 0
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
            errors.append(f"{account.get('full_name') or account['github_username']}: {error}")
    if not accounts:
        flash("Belum ada username GitHub yang dipetakan.", "warning")
    elif success_count:
        mode_note = f" {initial_count} akun mengambil riwayat dari awal." if initial_count else ""
        flash(
            f"GitHub tersinkron untuk {success_count} admin; {inserted_count} commit baru disimpan.{mode_note}",
            "success",
        )
    for error in errors[:5]:
        flash(error, "warning")
    return _performance_redirect_from_form()


@pengaturan_bp.route("/admin-performance/pdf")
@role_required("admin")
def admin_performance_pdf() -> Response:
    """Download the full leaderboard and the downloader's personal recap."""
    downloader = current_user() or {}
    downloader_id = int(downloader.get("id") or 0)
    if not downloader_id:
        return Response("Akun admin tidak valid.", status=400)

    feature_key = (request.args.get("feature") or "all").strip().lower() or "all"
    action = (request.args.get("action") or "").strip().upper() or None
    target_type = (request.args.get("target_type") or "").strip().upper() or None
    search = (request.args.get("search") or "").strip() or None
    period = _resolve_admin_performance_period()
    source_events = fetch_admin_activity_events(
        start=period["start"], end=period["end"]
    )
    common_filters = {
        "feature_key": feature_key,
        "action": action,
        "target_type": target_type,
        "search": search,
        "start": period["start"],
        "end": period["end"],
        "source_events": source_events,
    }

    # The requested admin_id is intentionally ignored in the PDF. Page one is
    # organization-wide; the personal page is bound to the authenticated user.
    organization = fetch_admin_performance_data(
        admin_id=None, detail_limit=50, **common_filters
    )
    personal = fetch_admin_performance_data(
        admin_id=downloader_id, detail_limit=50, **common_filters
    )
    leaderboard = _complete_admin_leaderboard(
        organization.get("leaderboard") or [], list_admin_users(), minimum_actions=0
    )
    github = _github_performance_context(period)
    attach_github_metrics(leaderboard, github["snapshots"])
    leaderboard = _score_admin_leaderboard(leaderboard)
    personal_snapshot = github["snapshots"].get(downloader_id, {})
    personal["github_username"] = personal_snapshot.get("github_username")
    personal["github_commits"] = personal_snapshot.get("commit_count")
    personal["github_coding_days"] = int(
        personal_snapshot.get("coding_day_count") or 0
    )
    personal["coding_points"] = personal["github_coding_days"] * 10
    personal["performance_total"] = (
        int((personal.get("summary") or {}).get("total_actions") or 0)
        + personal["coding_points"]
    )
    personal["organization_rank"] = next(
        (
            index
            for index, row in enumerate(leaderboard, start=1)
            if int(row.get("actor_user_id") or 0) == downloader_id
        ),
        None,
    )
    if personal.get("github_username"):
        hydrate_commit_line_stats(
            github["repository"], personal["github_username"],
            start=period["start"], end=period["end"],
        )
        personal["github_line_stats"] = get_commit_line_summary(
            github["repository"], personal["github_username"],
            start=period["start"], end=period["end"],
        )
    else:
        personal["github_line_stats"] = {
            "additions": 0, "deletions": 0, "changed_lines": 0,
            "measured_commits": 0, "total_commits": 0, "missing_commits": 0,
        }

    feature_label = (organization.get("feature_options") or {}).get(
        feature_key, feature_key
    )
    filter_parts = [
        f"Fitur: {feature_label}",
        f"Aksi: {action or 'Semua'}",
        f"Target: {target_type or 'Semua'}",
        f"GitHub: {github['repository']}",
    ]
    if search:
        filter_parts.append(f"Pencarian: {search}")
    pdf = build_admin_performance_pdf(
        leaderboard=leaderboard,
        personal=personal,
        downloader=downloader,
        period_label=_admin_performance_period_label(period),
        filters_label=" | ".join(filter_parts),
        generated_at=period["generated_at"],
        feature_options=organization.get("feature_options") or {},
    )
    if period["period_scope"] == "month":
        suffix = period["selected_month"]
    elif period["period_scope"] == "year":
        suffix = str(period["selected_year"])
    else:
        suffix = "seluruhnya"
    response = send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"performa-admin-{suffix}-{downloader_id}.pdf",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@pengaturan_bp.route("/admin-performance/admin/<int:admin_id>/events")
@role_required("admin")
def admin_performance_admin_events(admin_id: int) -> Response:
    feature_key = (request.args.get("feature") or "all").strip().lower() or "all"
    action = (request.args.get("action") or "").strip().upper() or None
    target_type = (request.args.get("target_type") or "").strip().upper() or None
    search = (request.args.get("search") or "").strip() or None
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    page = max(1, request.args.get("page", type=int) or 1)
    per_page = max(1, min(request.args.get("per_page", type=int) or 8, 25))

    payload = fetch_admin_activity_page(
        admin_id=admin_id,
        feature_key=feature_key,
        action=action,
        target_type=target_type,
        search=search,
        start=start,
        end=end,
        page=page,
        per_page=per_page,
    )
    return jsonify(payload)


@pengaturan_legacy_bp.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@pengaturan_legacy_bp.route("/<path:path>", methods=["GET", "POST"])
def legacy_settings_redirect(path: str) -> Response:
    """Keep existing settings bookmarks and form targets working."""
    target = url_for("pengaturan.admin_settings").rstrip("/")
    if path:
        target = f"{target}/{path}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8', errors='ignore')}"
    return redirect(target, code=307 if request.method == "POST" else 302)


@pengaturan_bp.route("/admin", methods=["GET", "POST"])
@pengaturan_bp.route("/", methods=["GET", "POST"])
@role_required("admin")
def admin_settings() -> Response | str:
    user = current_user() or {}
    if not user:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))

    user_id = user.get("id")

    if request.method == "POST":
        action = (request.form.get("action") or "save_settings").strip()
        active_tab = request.form.get("active_tab", "general")

        if action == "save_settings":
            settings_payload = {
                # General Settings
                "app_name": request.form.get("app_name", "").strip(),
                "app_subtitle": request.form.get("app_subtitle", "").strip(),
                "organization_name": request.form.get("organization_name", "").strip(),
                "support_email": request.form.get("support_email", "").strip(),
                "support_phone": request.form.get("support_phone", "").strip(),
                "maintenance_mode": "true" if request.form.get("maintenance_mode") == "on" else "false",
                "maintenance_message": request.form.get("maintenance_message", "").strip(),
                "session_timeout_minutes": request.form.get("session_timeout_minutes", "120").strip(),
                "allow_user_registration": "true" if request.form.get("allow_user_registration") == "on" else "false",

                # Notification Settings
                "telegram_notifications_enabled": "true" if request.form.get("telegram_notifications_enabled") == "on" else "false",
                "telegram_bot_token": request.form.get("telegram_bot_token", "").strip(),
                "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
                "whatsapp_notifications_enabled": "true" if request.form.get("whatsapp_notifications_enabled") == "on" else "false",
                "email_notifications_enabled": "true" if request.form.get("email_notifications_enabled") == "on" else "false",
                "notify_on_new_login": "true" if request.form.get("notify_on_new_login") == "on" else "false",
                "notify_on_system_error": "true" if request.form.get("notify_on_system_error") == "on" else "false",
                "notify_daily_summary": "true" if request.form.get("notify_daily_summary") == "on" else "false",

                # API Settings
                "whatsapp_api_endpoint": request.form.get("whatsapp_api_endpoint", "").strip(),
                "whatsapp_api_key": request.form.get("whatsapp_api_key", "").strip(),
                "telegram_webhook_url": request.form.get("telegram_webhook_url", "").strip(),
                "api_rate_limit_per_min": request.form.get("api_rate_limit_per_min", "60").strip(),
                "api_access_enabled": "true" if request.form.get("api_access_enabled") == "on" else "false",
            }

            success = update_system_settings(settings_payload, user_id=user_id)
            if success:
                flash("Pengaturan aplikasi berhasil diperbarui!", "success")
            else:
                flash("Gagal memperbarui pengaturan aplikasi.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab=active_tab))

        elif action == "save_token":
            raw_token = (request.form.get("bot_token") or "").strip()
            upsert_telegram_notification_settings(raw_token, user_id)
            update_system_settings({"telegram_bot_token": raw_token}, user_id=user_id)
            flash("Token bot Telegram berhasil disimpan.", "success")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "add_admins":
            admin_users = list_admin_users()
            admin_ids = {str(u.get("id")) for u in admin_users if u.get("id") is not None}
            raw_usernames = request.form.getlist("telegram_username[]")
            raw_admin_ids = request.form.getlist("dashboard_user_id[]")
            errors = []
            entries_map = {}

            for idx, (raw_username, raw_admin_id) in enumerate(zip(raw_usernames, raw_admin_ids), start=1):
                username = (raw_username or "").strip()
                admin_id = (raw_admin_id or "").strip()
                if not username and not admin_id:
                    continue

                normalized = username.lstrip("@").strip().lower()
                if not normalized:
                    errors.append(f"Username Telegram di baris {idx} kosong.")
                    continue
                if admin_id not in admin_ids:
                    errors.append(f"Admin dashboard belum dipilih untuk @{normalized}.")
                    continue

                entries_map[normalized] = int(admin_id)

            if entries_map:
                payload = [
                    {"telegram_username": username, "dashboard_user_id": admin_id}
                    for username, admin_id in entries_map.items()
                ]
                saved = upsert_telegram_admin_accounts(payload, created_by=user_id)
                flash(f"{saved} admin Telegram berhasil disimpan.", "success")
            else:
                if not errors:
                    flash("Tidak ada admin Telegram baru yang disimpan.", "warning")

            for error in errors:
                flash(error, "warning")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "delete_admin":
            mapping_id = request.form.get("mapping_id") or ""
            if mapping_id.isdigit():
                deleted = delete_telegram_admin_account(int(mapping_id))
                if deleted:
                    flash("Admin Telegram berhasil dihapus.", "success")
                else:
                    flash("Admin Telegram tidak ditemukan.", "warning")
            else:
                flash("ID admin tidak valid.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action == "delete_group":
            group_id = request.form.get("group_id") or ""
            if group_id.isdigit():
                deleted = delete_telegram_notification_group(int(group_id))
                if deleted:
                    flash("Grup Telegram berhasil dihapus.", "success")
                else:
                    flash("Grup Telegram tidak ditemukan.", "warning")
            else:
                flash("ID grup tidak valid.", "danger")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

        elif action in ["test_notification", "test_telegram"]:
            raw_message = request.form.get("test_message") or ""
            result = send_test_notification(raw_message)
            if result.get("skipped") == "token_missing":
                flash("Token bot Telegram belum diisi.", "warning")
            else:
                sent = int(result.get("sent") or 0)
                group_sent = int(result.get("group_sent") or 0)
                missing = result.get("missing_usernames") or []
                if sent == 0 and group_sent == 0:
                    flash("Tes notifikasi belum terkirim. Pastikan admin sudah chat bot atau grup terdaftar.", "warning")
                else:
                    flash(f"Tes notifikasi terkirim ke {sent} admin dan {group_sent} grup.", "success")
                if missing:
                    flash(f"{len(missing)} admin belum pernah chat bot.", "warning")
            return redirect(url_for("pengaturan.admin_settings", tab="notification"))

    raw_settings = get_all_system_settings()
    settings_dict = {k: v["setting_value"] for k, v in raw_settings.items()}
    telegram_settings = fetch_telegram_notification_settings() or {}
    admin_users = list_admin_users()
    telegram_admins = list_telegram_admin_accounts()
    telegram_groups = list_telegram_notification_groups()
    system_info = get_system_diagnostic_info()
    active_tab = request.args.get("tab", "general")

    return render_template(
        "pengaturan/admin_settings.html",
        settings=settings_dict,
        settings_raw=raw_settings,
        telegram_settings=telegram_settings,
        admin_users=admin_users,
        telegram_admins=telegram_admins,
        telegram_groups=telegram_groups,
        system_info=system_info,
        active_tab=active_tab,
        page_title="Pengaturan Aplikasi Dashboard",
    )


@pengaturan_bp.route("/users", methods=["GET", "POST"])
@portal_routes._preview_access_required
def manage_users() -> Response:
    """Manage dashboard accounts from the central settings module."""
    from dashboard.user_management import handle_manage_users

    return handle_manage_users(
        actor=portal_routes._preview_admin_actor(),
        base_template="pengaturan/base_pengaturan.html",
        read_only=portal_routes._is_preview_read_only_session(),
    )


@pengaturan_bp.route("/preview-akun", methods=["GET"])
@portal_routes._preview_access_required
def preview_accounts() -> Response:
    """Open the account preview workspace from central settings."""
    return portal_routes._render_preview_accounts()


@pengaturan_bp.route("/public-api", methods=["GET", "POST"])
@role_required("admin")
def public_api_settings() -> Response | str:
    user = current_user() or {}
    if not user:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))

    user_id = user.get("id")

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "create_key":
            client_name = (request.form.get("client_name") or "").strip()
            contact_email = (request.form.get("contact_email") or "").strip()
            notes = (request.form.get("notes") or "").strip()
            scopes = request.form.getlist("scopes[]") or ["schools:read"]

            if not client_name:
                flash("Nama instansi / client wajib diisi.", "warning")
            else:
                created = create_public_api_key(
                    client_name=client_name,
                    contact_email=contact_email,
                    scopes=scopes,
                    notes=notes,
                    created_by=user_id,
                )
                if created:
                    flash(f"Public API Key untuk '{client_name}' berhasil dibuat!", "success")
                else:
                    flash("Gagal membuat Public API Key.", "danger")
            return redirect(url_for("pengaturan.public_api_settings"))

        elif action == "toggle_status":
            key_id = request.form.get("key_id") or ""
            if key_id.isdigit():
                toggled = toggle_public_api_key_status(int(key_id))
                if toggled:
                    flash("Status Public API Key berhasil diperbarui.", "success")
                else:
                    flash("API Key tidak ditemukan.", "warning")
            return redirect(url_for("pengaturan.public_api_settings"))

        elif action == "delete_key":
            key_id = request.form.get("key_id") or ""
            if key_id.isdigit():
                deleted = delete_public_api_key(int(key_id))
                if deleted:
                    flash("Public API Key berhasil dihapus.", "success")
                else:
                    flash("API Key tidak ditemukan.", "warning")
            return redirect(url_for("pengaturan.public_api_settings"))

    api_keys = list_public_api_keys()
    return render_template(
        "pengaturan/public_api.html",
        api_keys=api_keys,
        page_title="API Publik Instansi",
    )


@pengaturan_bp.route("/api/v1/public/schools", methods=["GET"])
def public_api_schools() -> Response:
    """Public JSON API Endpoint to fetch school data for authorized external clients."""
    # Read API Key from HTTP Header 'X-API-Key' or URL parameter 'api_key'
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key") or ""

    verified = verify_public_api_key(api_key, required_scope="schools:read")
    if not verified:
        return jsonify({
            "status": "error",
            "message": "Autentikasi gagal. API Key tidak valid, nonaktif, atau tidak memiliki izin akses (schools:read).",
            "code": 401,
        }), 401

    schools = fetch_public_schools_api_data()
    return jsonify({
        "status": "success",
        "client": verified.get("client_name"),
        "total": len(schools),
        "data": schools,
    })
