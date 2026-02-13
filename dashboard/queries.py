from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import has_request_context, session
from psycopg2.extras import DictRow, Json

from .db_access import get_cursor
from account_status import ACCOUNT_STATUS_CHOICES

_UNSET = object()

TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "dan",
    "yang",
    "atau",
    "untuk",
    "dengan",
    "pada",
    "dari",
    "kami",
    "kita",
    "kamu",
    "anda",
    "saya",
    "aku",
    "dia",
    "itu",
    "ini",
    "jadi",
    "apa",
    "berapa",
    "bagaimana",
    "kapan",
    "dimana",
    "mengapa",
    "apakah",
    "sudah",
    "belum",
    "akan",
    "bisa",
    "mohon",
    "tolong",
    "terima",
    "kasih",
    "ya",
    "tidak",
    "iya",
    "oke",
    "ok",
    "hai",
    "halo",
    "selamat",
    "malam",
    "pagi",
    "siang",
    "sore",
    "bot",
    "aska",
}

_CHAT_TOPIC_AVAILABLE: Optional[bool] = None
_TESTER_IDS_CACHE: Optional[List[int]] = None


def _load_tester_ids() -> List[int]:
    """Parse tester user_id list from environment."""
    global _TESTER_IDS_CACHE
    if _TESTER_IDS_CACHE is not None:
        return _TESTER_IDS_CACHE

    raw_value = os.getenv("DASHBOARD_TESTER_IDS", "") or ""
    candidates = re.split(r"[,\s;]+", raw_value.strip())
    parsed: List[int] = []
    for item in candidates:
        if not item:
            continue
        try:
            parsed.append(int(item))
        except ValueError:
            continue
    _TESTER_IDS_CACHE = parsed
    return parsed


def _no_tester_active() -> bool:
    """Return True when the current request should hide tester data."""
    if not has_request_context():
        return False
    user = session.get("user") or {}
    return bool(user.get("no_tester_enabled"))


def _tester_condition(column: str = "user_id") -> Tuple[str, List[Any]]:
    """
    Build a SQL condition snippet (without prefix) to exclude tester user_ids.
    Returns the condition string and parameter list (single list of ids) when active.
    """
    if not _no_tester_active():
        return "", []
    tester_ids = _load_tester_ids()
    if not tester_ids:
        return "", []
    return f"({column} IS NULL OR {column} <> ALL(%s))", [tester_ids]


def chat_topic_available() -> bool:
    """Check once whether chat_logs table has topic column."""
    global _CHAT_TOPIC_AVAILABLE
    if _CHAT_TOPIC_AVAILABLE is not None:
        return _CHAT_TOPIC_AVAILABLE
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'chat_logs'
              AND column_name = 'topic'
            LIMIT 1
            """
        )
        _CHAT_TOPIC_AVAILABLE = cur.fetchone() is not None
    return _CHAT_TOPIC_AVAILABLE
BULLYING_STATUSES = (
    'pending',
    'in_progress',
    'resolved',
    'spam',
)

CORRUPTION_STATUSES = (
    'open',
    'in_progress',
    'resolved',
    'archived',
)

PSYCH_STATUSES = (
    'open',
    'in_progress',
    'resolved',
    'archived',
)

PSYCH_SEVERITIES = (
    'general',
    'elevated',
    'critical',
)

@dataclass
class ChatFilters:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    role: Optional[str] = None
    search: Optional[str] = None
    user_id: Optional[int] = None
    topic: Optional[str] = None

def _apply_filters(conditions: List[str], params: List[Any], filters: ChatFilters) -> None:
    if filters.start:
        conditions.append("created_at >= %s")
        params.append(filters.start)
    if filters.end:
        conditions.append("created_at <= %s")
        params.append(filters.end)
    if filters.role:
        conditions.append("role = %s")
        params.append(filters.role)
    if filters.user_id:
        conditions.append("user_id = %s")
        params.append(filters.user_id)
    if filters.search:
        conditions.append("text ILIKE %s")
        params.append(f"%{filters.search}%")
    if filters.topic and chat_topic_available():
        conditions.append("topic = %s")
        params.append(filters.topic)

def fetch_overview_metrics(window_days: int = 7) -> Dict[str, Any]:
    """Aggregate key performance indicators for the dashboard landing page."""
    window_days = max(1, window_days)
    interval = timedelta(days=window_days)

    bullying_rows: List[Dict[str, Any]] = []
    escalated_total = 0

    with get_cursor() as cur:
        clause, params = _tester_condition("user_id")
        tester_param = params[0] if params else None

        query = "SELECT COUNT(*) AS total_messages FROM chat_logs"
        if clause:
            query += f" WHERE {clause}"
        cur.execute(query, (tester_param,) if tester_param is not None else ())
        total_messages = cur.fetchone()["total_messages"]

        query = (
            "SELECT COUNT(*) AS total_incoming_messages "
            "FROM chat_logs WHERE role = 'user'"
        )
        query_params: List[Any] = []
        if clause:
            query += f" AND {clause}"
            query_params = [tester_param]
        cur.execute(query, tuple(query_params))
        total_incoming_messages = cur.fetchone()["total_incoming_messages"]

        def _distinct_users(interval_clause: str) -> int:
            base_query = (
                "SELECT COUNT(DISTINCT user_id) AS unique_users "
                "FROM chat_logs WHERE role = 'user'"
            )
            query_params: List[Any] = []
            if interval_clause:
                base_query += f" AND {interval_clause}"
            if clause:
                base_query += f" AND {clause}"
                query_params.append(tester_param)
            cur.execute(base_query, tuple(query_params))
            return cur.fetchone()["unique_users"]

        unique_users_all = _distinct_users("")
        unique_users_today = _distinct_users("DATE(created_at) = CURRENT_DATE")
        unique_users_7d = _distinct_users("created_at >= NOW() - INTERVAL '7 days'")
        unique_users_30d = _distinct_users("created_at >= NOW() - INTERVAL '30 days'")
        unique_users_365d = _distinct_users("created_at >= NOW() - INTERVAL '365 days'")

        query = (
            "SELECT "
            "    AVG(response_time_ms)::float AS avg_response, "
            "    percentile_cont(0.9) WITHIN GROUP (ORDER BY response_time_ms) AS p90_response "
            "FROM chat_logs "
            "WHERE response_time_ms IS NOT NULL"
        )
        query_params = []
        if clause:
            query += f" AND {clause}"
            query_params = [tester_param]
        cur.execute(query, tuple(query_params))
        response_stats = cur.fetchone()

        active_today = unique_users_today

        cur.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM bullying_reports
            GROUP BY status
            """
        )
        bullying_rows = cur.fetchall()
        cur.execute(
            """
            SELECT COUNT(*) AS escalated_total
            FROM bullying_reports
            WHERE escalated = TRUE
            """
        )
        escalated_total = cur.fetchone()["escalated_total"] or 0

    avg_response = response_stats["avg_response"] or 0.0
    p90_response = response_stats["p90_response"] or 0.0

    bullying_summary = {status: 0 for status in BULLYING_STATUSES}
    bullying_total = 0
    for row in bullying_rows:
        status = (row.get("status") or "").lower()
        count = int(row.get("total") or 0)
        if status in bullying_summary:
            bullying_summary[status] = count
            bullying_total += count
    bullying_summary["total"] = bullying_total
    bullying_summary["escalated"] = int(escalated_total or 0)

    corruption_summary = fetch_corruption_summary()
    psych_summary = fetch_psych_summary()
    corruption_active_total = int(
        (corruption_summary.get("total", 0) - corruption_summary.get("archived", 0))
        if corruption_summary
        else 0
    )
    bullying_active_total = int(bullying_total - bullying_summary.get("spam", 0))
    psych_active_total = int(psych_summary.get("total", 0)) if psych_summary else 0

    return {
        "total_messages": int(total_messages or 0),
        "total_incoming_messages": int(total_incoming_messages or 0),
        "unique_users": int(unique_users_all or 0),
        "unique_users_all": int(unique_users_all or 0),
        "unique_users_today": int(unique_users_today or 0),
        "unique_users_7d": int(unique_users_7d or 0),
        "unique_users_30d": int(unique_users_30d or 0),
        "unique_users_365d": int(unique_users_365d or 0),
        "window_days": window_days,
        "avg_response_ms": round(avg_response, 2),
        "p90_response_ms": round(p90_response, 2),
        "active_today": int(active_today or 0),
        "bullying_total": bullying_total,
        "bullying_pending": bullying_summary['pending'],
        "bullying_in_progress": bullying_summary['in_progress'],
        "bullying_resolved": bullying_summary['resolved'],
        "bullying_spam": bullying_summary['spam'],
        "bullying_summary": bullying_summary,
        "bullying_active_total": bullying_active_total,
        "corruption_summary": corruption_summary,
        "corruption_active_total": corruption_active_total,
        "psych_summary": psych_summary,
        "psych_active_total": psych_active_total,
    }

def fetch_daily_activity(days: int = 14, role: Optional[str] = None) -> List[Dict[str, Any]]:
    days = max(1, days)
    params: List[Any] = [f"{days} days"]
    query = [
        "SELECT DATE(created_at) AS day, COUNT(*) AS messages",
        "FROM chat_logs",
        "WHERE created_at >= NOW() - %s::interval",
    ]
    if role:
        query.append("AND role = %s")
        params.append(role)
    clause, clause_params = _tester_condition("user_id")
    if clause:
        query.append(f"AND {clause}")
        params.extend(clause_params)
    query.extend(
        [
            "GROUP BY day",
            "ORDER BY day ASC",
        ]
    )
    with get_cursor() as cur:
        cur.execute("\n".join(query), tuple(params))
        rows = cur.fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        count = int(row.get("messages") or 0)
        if count <= 0:
            continue
        result.append({"day": row.get("day"), "messages": count})
    return result

def fetch_recent_questions(limit: int = 10) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT id, user_id, username, text, created_at",
            "FROM chat_logs",
            "WHERE role = 'user'",
        ]
        if clause:
            query_parts.append(f"AND {clause}")
        query_parts.extend(
            [
                "ORDER BY created_at DESC",
                "LIMIT %s",
            ]
        )
        params: List[Any] = [*clause_params, limit]
        cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()
    return [dict(row) for row in rows]

def fetch_top_users(limit: int = 5) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT user_id, COALESCE(username, 'Unknown') AS username, COUNT(*) AS messages",
            "FROM chat_logs",
            "WHERE role = 'user'",
        ]
        if clause:
            query_parts.append(f"AND {clause}")
        query_parts.extend(
            [
                "GROUP BY user_id, username",
                "ORDER BY messages DESC",
                "LIMIT %s",
            ]
        )
        params: List[Any] = [*clause_params, limit]
        cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()
    return [dict(row) for row in rows]

def fetch_top_keywords(limit: int = 10, days: int = 14, min_length: int = 3) -> List[Dict[str, Any]]:
    """Return most frequent keywords from user messages within the given time window."""
    days = max(1, days)
    limit = max(1, limit)
    min_length = max(1, min_length)

    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT text",
            "FROM chat_logs",
            "WHERE role = 'user'",
            "  AND text IS NOT NULL",
            "  AND text <> ''",
            "  AND created_at >= NOW() - %s::interval",
        ]
        if clause:
            query_parts.append(f"  AND {clause}")
        params: List[Any] = [f"{days} days", *clause_params]
        cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()

    counter: Counter[str] = Counter()
    for row in rows:
        text_value = (row["text"] or "").lower()
        for token in TOKEN_PATTERN.findall(text_value):
            if len(token) < min_length or token.isdigit() or token in STOPWORDS:
                continue
            counter[token] += 1

    return [
        {"keyword": keyword, "count": count}
        for keyword, count in counter.most_common(limit)
    ]

def fetch_chat_logs(
    filters: ChatFilters,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    conditions: List[str] = []
    params: List[Any] = []
    _apply_filters(conditions, params, filters)

    tester_clause, tester_params = _tester_condition("user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    select_columns = "id, user_id, username, text, role, created_at, response_time_ms"
    if chat_topic_available():
        select_columns = "id, user_id, username, text, role, topic, created_at, response_time_ms"

    query = (
        f"SELECT {select_columns} "
        "FROM chat_logs"
        f"{where_clause} "
        "ORDER BY created_at DESC "
        "LIMIT %s OFFSET %s"
    )
    with get_cursor() as cur:
        cur.execute(query, (*params, limit, offset))
        rows = cur.fetchall()

        cur.execute(f"SELECT COUNT(*) FROM chat_logs{where_clause}", params)
        total = cur.fetchone()[0]

    return [dict(row) for row in rows], int(total or 0)

def fetch_conversation_thread(user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    if _no_tester_active() and user_id in set(_load_tester_ids()):
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, username, text, role, created_at, response_time_ms
            FROM chat_logs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
    rows.reverse()
    return rows


def fetch_all_chat_users() -> List[Dict[str, Any]]:
    """Fetches all users who have sent messages, with their message counts."""
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT",
            "    user_id,",
            "    COALESCE(username, 'Unknown') AS username,",
            "    COUNT(*) AS message_count",
            "FROM chat_logs",
            "WHERE role = 'user'",
        ]
        if clause:
            query_parts.append(f"AND {clause}")
        query_parts.extend(
            [
                "GROUP BY user_id, username",
                "ORDER BY MAX(created_at) DESC",
            ]
        )
        cur.execute("\n".join(query_parts), tuple(clause_params))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_twitter_overview(window_days: int = 7, bot_user_id: Optional[int] = None) -> Dict[str, Any]:
    """Aggregate metrik penting untuk operasional Twitter/X."""
    if not chat_topic_available():
        return {
            "window_days": window_days,
            "total_mentions": 0,
            "total_replies": 0,
            "total_users": 0,
            "mentions_window": 0,
            "replies_window": 0,
            "users_window": 0,
            "mentions_24h": 0,
            "replies_24h": 0,
            "mentions_today": 0,
            "replies_today": 0,
            "avg_response_ms": None,
            "p90_response_ms": None,
            "backlog": 0,
            "reply_rate": 0.0,
            "last_mention": None,
            "last_reply": None,
            "autopost_total": 0,
            "autopost_window": 0,
            "autopost_24h": 0,
            "autopost_today": 0,
            "last_autopost": None,
        }

    window_days = max(1, window_days)
    window_interval = f"{window_days} days"

    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        overview_query = """
            SELECT
                COUNT(*) FILTER (WHERE role = 'user') AS mentions_total,
                COUNT(*) FILTER (WHERE role = 'aska') AS replies_total,
                COUNT(DISTINCT user_id) FILTER (WHERE role = 'user') AS users_total,
                COUNT(*) FILTER (WHERE role = 'user' AND created_at >= NOW() - %s::interval) AS mentions_window,
                COUNT(*) FILTER (WHERE role = 'aska' AND created_at >= NOW() - %s::interval) AS replies_window,
                COUNT(DISTINCT user_id) FILTER (WHERE role = 'user' AND created_at >= NOW() - %s::interval) AS users_window,
                COUNT(*) FILTER (WHERE role = 'user' AND created_at >= NOW() - INTERVAL '1 day') AS mentions_24h,
                COUNT(*) FILTER (WHERE role = 'aska' AND created_at >= NOW() - INTERVAL '1 day') AS replies_24h,
                COUNT(*) FILTER (WHERE role = 'user' AND DATE(created_at) = CURRENT_DATE) AS mentions_today,
                COUNT(*) FILTER (WHERE role = 'aska' AND DATE(created_at) = CURRENT_DATE) AS replies_today,
                AVG(response_time_ms) FILTER (WHERE role = 'aska' AND response_time_ms IS NOT NULL) AS avg_response_ms,
                percentile_cont(0.9) WITHIN GROUP (ORDER BY response_time_ms)
                    FILTER (WHERE role = 'aska' AND response_time_ms IS NOT NULL) AS p90_response_ms
            FROM chat_logs
            WHERE topic = 'twitter'
        """.strip()
        params: List[Any] = [window_interval, window_interval, window_interval]
        if clause:
            overview_query += f" AND {clause}"
            params.extend(clause_params)
        cur.execute(overview_query, tuple(params))
        overview_row = cur.fetchone() or {}

        mention_query = [
            "SELECT id, user_id, username, text, created_at",
            "FROM chat_logs",
            "WHERE topic = 'twitter' AND role = 'user'",
        ]
        mention_params: List[Any] = []
        if clause:
            mention_query.append(f"AND {clause}")
            mention_params.extend(clause_params)
        mention_query.extend(["ORDER BY created_at DESC", "LIMIT 1"])
        cur.execute("\n".join(mention_query), tuple(mention_params))
        last_mention = cur.fetchone()

        reply_query = [
            "SELECT id, user_id, username, text, created_at, response_time_ms",
            "FROM chat_logs",
            "WHERE topic = 'twitter' AND role = 'aska'",
        ]
        reply_params: List[Any] = []
        if bot_user_id:
            reply_query.append("AND (user_id IS NULL OR user_id <> %s)")
            reply_params.append(bot_user_id)
        if clause:
            reply_query.append(f"AND {clause}")
            reply_params.extend(clause_params)
        reply_query.extend(["ORDER BY created_at DESC", "LIMIT 1"])
        cur.execute("\n".join(reply_query), tuple(reply_params))
        last_reply = cur.fetchone()

        autopost_total = autopost_window = autopost_24h = autopost_today = 0
        last_autopost = None
        if bot_user_id:
            autopost_query = [
                "SELECT",
                "    COUNT(*) AS total,",
                "    COUNT(*) FILTER (WHERE created_at >= NOW() - %s::interval) AS window,",
                "    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day') AS day_24h,",
                "    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) AS today",
                "FROM chat_logs",
                "WHERE topic = 'twitter'",
                "  AND role = 'aska'",
                "  AND user_id = %s",
            ]
            autopost_params: List[Any] = [window_interval, bot_user_id]
            if clause:
                autopost_query.append(f"  AND {clause}")
                autopost_params.extend(clause_params)
            cur.execute("\n".join(autopost_query), tuple(autopost_params))
            autopost_row = cur.fetchone() or {}

            autopost_last_query = [
                "SELECT id, user_id, username, text, created_at",
                "FROM chat_logs",
                "WHERE topic = 'twitter'",
                "  AND role = 'aska'",
                "  AND user_id = %s",
            ]
            autopost_last_params: List[Any] = [bot_user_id]
            if clause:
                autopost_last_query.append(f"  AND {clause}")
                autopost_last_params.extend(clause_params)
            autopost_last_query.extend(["ORDER BY created_at DESC", "LIMIT 1"])
            cur.execute("\n".join(autopost_last_query), tuple(autopost_last_params))
            last_autopost = cur.fetchone()
        else:
            autopost_row = {}

    def _coerce_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    avg_response = overview_row.get("avg_response_ms")
    p90_response = overview_row.get("p90_response_ms")

    total_mentions = _coerce_int(overview_row.get("mentions_total"))
    total_replies_raw = _coerce_int(overview_row.get("replies_total"))
    replies_window_raw = _coerce_int(overview_row.get("replies_window"))
    replies_24h_raw = _coerce_int(overview_row.get("replies_24h"))
    replies_today_raw = _coerce_int(overview_row.get("replies_today"))

    autopost_total = _coerce_int(autopost_row.get("total"))
    autopost_window = _coerce_int(autopost_row.get("window"))
    autopost_24h = _coerce_int(autopost_row.get("day_24h"))
    autopost_today = _coerce_int(autopost_row.get("today"))

    total_replies = max(0, total_replies_raw - autopost_total)
    replies_window = max(0, replies_window_raw - autopost_window)
    replies_24h = max(0, replies_24h_raw - autopost_24h)
    replies_today = max(0, replies_today_raw - autopost_today)

    backlog = max(0, total_mentions - total_replies)
    reply_rate = 0.0
    if total_mentions:
        reply_rate = round(min(1.0, total_replies / total_mentions), 3)

    return {
        "window_days": window_days,
        "total_mentions": total_mentions,
        "total_replies": total_replies,
        "total_users": _coerce_int(overview_row.get("users_total")),
        "mentions_window": _coerce_int(overview_row.get("mentions_window")),
        "replies_window": replies_window,
        "users_window": _coerce_int(overview_row.get("users_window")),
        "mentions_24h": _coerce_int(overview_row.get("mentions_24h")),
        "replies_24h": replies_24h,
        "mentions_today": _coerce_int(overview_row.get("mentions_today")),
        "replies_today": replies_today,
        "avg_response_ms": float(avg_response) if avg_response is not None else None,
        "p90_response_ms": float(p90_response) if p90_response is not None else None,
        "backlog": backlog,
        "reply_rate": reply_rate,
        "last_mention": dict(last_mention) if last_mention else None,
        "last_reply": dict(last_reply) if last_reply else None,
        "autopost_total": autopost_total,
        "autopost_window": autopost_window,
        "autopost_24h": autopost_24h,
        "autopost_today": autopost_today,
        "last_autopost": dict(last_autopost) if last_autopost else None,
    }


def fetch_twitter_activity(days: int = 30) -> List[Dict[str, Any]]:
    """Ambil aktivitas harian mention dan balasan untuk topik Twitter."""
    if not chat_topic_available():
        return []
    days = max(1, days)
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT",
            "    DATE(created_at) AS day,",
            "    COUNT(*) FILTER (WHERE role = 'user') AS mentions,",
            "    COUNT(*) FILTER (WHERE role = 'aska') AS replies",
            "FROM chat_logs",
            "WHERE topic = 'twitter'",
            "  AND created_at >= NOW() - %s::interval",
        ]
        if clause:
            query_parts.append(f"  AND {clause}")
        query_parts.extend(["GROUP BY day", "ORDER BY day ASC"])
        params: List[Any] = [f"{days} days", *clause_params]
        cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()
    return [
        {
            "day": row.get("day"),
            "mentions": int(row.get("mentions") or 0),
            "replies": int(row.get("replies") or 0),
        }
        for row in rows
    ]


def fetch_twitter_top_users(limit: int = 8) -> List[Dict[str, Any]]:
    """Pengguna Twitter yang paling sering menyebut bot."""
    if not chat_topic_available():
        return []
    limit = max(1, limit)
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query_parts = [
            "SELECT",
            "    user_id,",
            "    COALESCE(NULLIF(username, ''), 'Unknown') AS username,",
            "    COUNT(*) AS mentions,",
            "    MAX(created_at) AS last_seen",
            "FROM chat_logs",
            "WHERE topic = 'twitter'",
            "  AND role = 'user'",
        ]
        if clause:
            query_parts.append(f"  AND {clause}")
        query_parts.extend(
            [
                "GROUP BY user_id, username",
                "ORDER BY mentions DESC, last_seen DESC",
                "LIMIT %s",
            ]
        )
        params: List[Any] = [*clause_params, limit]
        cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_twitter_worker_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Ambil log terbaru dari worker Twitter yang tersimpan di database."""
    limit = max(1, min(int(limit or 100), 500))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, level, message, context, tweet_id, twitter_user_id, created_at
            FROM twitter_worker_logs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    result: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        context = payload.get("context")
        if isinstance(context, dict):
            payload["context"] = dict(context)
        else:
            payload["context"] = None
        result.append(payload)
    return result



def fetch_bullying_summary() -> Dict[str, int]:
    """Return aggregated counts of bullying reports by status."""
    summary = {status: 0 for status in BULLYING_STATUSES}
    total = 0
    escalated_total = 0
    with get_cursor() as cur:
        clause, clause_params = _tester_condition("user_id")
        query = [
            "SELECT status, COUNT(*) AS total",
            "FROM bullying_reports",
        ]
        if clause:
            query.append(f"WHERE {clause}")
        query.append("GROUP BY status")
        cur.execute("\n".join(query), tuple(clause_params))
        rows = cur.fetchall()
        esc_query = "SELECT COUNT(*) FROM bullying_reports WHERE escalated = TRUE"
        esc_params: List[Any] = []
        if clause:
            esc_query += f" AND {clause}"
            esc_params.extend(clause_params)
        cur.execute(esc_query, tuple(esc_params))
        escalated_total = cur.fetchone()[0]
    for row in rows:
        status = (row.get('status') or '').lower()
        count = int(row.get('total') or 0)
        if status in summary:
            summary[status] = count
            total += count
    summary['total'] = total
    summary['escalated'] = int(escalated_total or 0)
    return summary


def fetch_pending_bullying_count() -> int:
    """Shortcut to obtain the number of pending bullying reports."""
    return fetch_bullying_summary().get('pending', 0)


def fetch_psych_summary() -> Dict[str, Any]:
    """Return aggregated counts of psychological reports by status and severity."""
    summary = {status: 0 for status in PSYCH_STATUSES}
    severity_counts = {severity: 0 for severity in PSYCH_SEVERITIES}
    total = 0
    clause, clause_params = _tester_condition("user_id")

    with get_cursor() as cur:
        status_query = [
            "SELECT status, COUNT(*) AS total",
            "FROM psych_reports",
        ]
        if clause:
            status_query.append(f"WHERE {clause}")
        status_query.append("GROUP BY status")
        cur.execute("\n".join(status_query), tuple(clause_params))
        status_rows = cur.fetchall()

        severity_query = [
            "SELECT severity, COUNT(*) AS total",
            "FROM psych_reports",
            "WHERE status IS NULL OR status <> 'archived'",
        ]
        severity_params: List[Any] = []
        if clause:
            severity_query.append(f"  AND {clause}")
            severity_params.extend(clause_params)
        severity_query.append("GROUP BY severity")
        cur.execute("\n".join(severity_query), tuple(severity_params))
        severity_rows = cur.fetchall()

    for row in status_rows:
        status = (row.get('status') or '').lower()
        count = int(row.get('total') or 0)
        if status in summary:
            summary[status] = count
            if status != "archived":
                total += count

    for row in severity_rows:
        severity = (row.get('severity') or '').lower()
        count = int(row.get('total') or 0)
        if severity in severity_counts:
            severity_counts[severity] = count

    summary['total'] = total
    summary['severity'] = severity_counts
    summary['critical'] = severity_counts.get('critical', 0)
    summary['elevated'] = severity_counts.get('elevated', 0)
    summary['general'] = severity_counts.get('general', 0)
    return summary


def fetch_pending_psych_count() -> int:
    """Return number of open psychological reports."""
    clause, clause_params = _tester_condition("user_id")
    query = "SELECT COUNT(*) FROM psych_reports WHERE status = 'open'"
    params: List[Any] = []
    if clause:
        query += f" AND {clause}"
        params.extend(clause_params)
    with get_cursor() as cur:
        cur.execute(query, tuple(params))
        row = cur.fetchone()
    return int(row[0] if row else 0)


def fetch_bullying_reports(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated bullying reports ordered by priority and recency."""
    status_filter = None
    if status:
        normalized = status.lower()
        if normalized not in BULLYING_STATUSES:
            raise ValueError(f"Status bullying tidak dikenal: {status}")
        status_filter = normalized

    conditions: List[str] = []
    params: List[Any] = []
    if status_filter:
        conditions.append('br.status = %s')
        params.append(status_filter)
    tester_clause, tester_params = _tester_condition("br.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = ''
    if conditions:
        where_clause = ' WHERE ' + ' AND '.join(conditions)

    query = (
        """
        SELECT
            br.id,
            br.chat_log_id,
            br.user_id,
            br.username,
            br.description,
            br.status,
            br.priority,
            br.notes,
            br.created_at,
            br.updated_at,
            br.last_updated_by,
            br.category,
            br.severity,
            br.metadata,
            br.assigned_to,
            br.due_at,
            br.resolved_at,
            br.escalated,
            cl.created_at AS chat_created_at
        FROM bullying_reports br
        LEFT JOIN chat_logs cl ON cl.id = br.chat_log_id
        """
        + where_clause
        + " ORDER BY br.escalated DESC, br.priority DESC, br.created_at DESC LIMIT %s OFFSET %s"
    )

    with get_cursor() as cur:
        cur.execute(query, (*params, limit, offset))
        rows = cur.fetchall()
        cur.execute(
            "SELECT COUNT(*) FROM bullying_reports br" + where_clause,
            params,
        )
        total = cur.fetchone()[0]

    records: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        description = record.get("description") or ""
        if description:
            preview = description.split("\n\n", 1)[0].strip()
        else:
            preview = ""
        record["description_preview"] = preview
        records.append(record)

    return records, int(total or 0)


def fetch_psych_reports(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated psychological reports ordered by severity and recency."""
    conditions: List[str] = []
    params: List[Any] = []
    group_expr = "COALESCE(CAST(pr.user_id AS TEXT), CONCAT('report-', pr.id))"

    if status:
        normalized_status = status.lower()
        if normalized_status not in PSYCH_STATUSES:
            raise ValueError(f"Status laporan psikolog tidak dikenal: {status}")
        conditions.append("pr.status = %s")
        params.append(normalized_status)

    if severity:
        normalized_severity = severity.lower()
        if normalized_severity not in PSYCH_SEVERITIES:
            raise ValueError(f"Tingkat keparahan tidak dikenal: {severity}")
        conditions.append("pr.severity = %s")
        params.append(normalized_severity)
    tester_clause, tester_params = _tester_condition("pr.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    filtered_cte = (
        """
        WITH filtered AS (
            SELECT
                pr.*,
                cl.created_at AS chat_created_at,
                {group_expr} AS group_key,
                ROW_NUMBER() OVER (
                    PARTITION BY {group_expr}
                    ORDER BY pr.created_at DESC
                ) AS row_no
            FROM psych_reports pr
            LEFT JOIN chat_logs cl ON cl.id = pr.chat_log_id
            {where_clause}
        )
        """
    ).format(group_expr=group_expr, where_clause=where_clause)

    query = (
        filtered_cte
        + """
        SELECT
            id,
            chat_log_id,
            user_id,
            username,
            message,
            summary,
            severity,
            status,
            metadata,
            created_at,
            updated_at,
            chat_created_at,
            group_key
        FROM filtered
        WHERE row_no = 1
        ORDER BY CASE WHEN severity = 'critical' THEN 2 WHEN severity = 'elevated' THEN 1 ELSE 0 END DESC, created_at DESC
        LIMIT %s OFFSET %s
        """
    )

    with get_cursor() as cur:
        cur.execute(query, (*params, limit, offset))
        rows = cur.fetchall()
        count_query = (
            filtered_cte
            + "SELECT COUNT(DISTINCT group_key) FROM filtered"
        )
        cur.execute(count_query, params)
        total = cur.fetchone()[0] if cur.rowcount else 0

    records: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        message_text = record.get("message") or ""
        if message_text:
            message_preview = message_text.split("\n\n", 1)[0].strip()
        else:
            message_preview = ""
        summary_text = record.get("summary") or ""
        if summary_text:
            summary_preview = summary_text.split("\n\n", 1)[0].strip()
        else:
            summary_preview = message_preview
        record["message_preview"] = message_preview
        record["summary_preview"] = summary_preview or message_preview
        records.append(record)

    return records, int(total or 0)


def fetch_psych_group_reports(
    *,
    user_id: Optional[int] = None,
    report_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return all reports belonging to a user (or fallback single report)."""
    if user_id is None and report_id is None:
        raise ValueError("Either user_id or report_id must be provided")

    tester_clause, tester_params = _tester_condition("pr.user_id")

    with get_cursor() as cur:
        if user_id is not None:
            query_parts = [
                "SELECT",
                "    pr.id,",
                "    pr.chat_log_id,",
                "    pr.user_id,",
                "    pr.username,",
                "    pr.message,",
                "    pr.summary,",
                "    pr.severity,",
                "    pr.status,",
                "    pr.metadata,",
                "    pr.created_at,",
                "    pr.updated_at,",
                "    cl.created_at AS chat_created_at",
                "FROM psych_reports pr",
                "LEFT JOIN chat_logs cl ON cl.id = pr.chat_log_id",
                "WHERE pr.user_id = %s",
            ]
            params: List[Any] = [user_id]
            if tester_clause:
                query_parts.append(f"  AND {tester_clause}")
                params.extend(tester_params)
            query_parts.append("ORDER BY pr.created_at DESC")
            cur.execute("\n".join(query_parts), tuple(params))
        else:
            query_parts = [
                "SELECT",
                "    pr.id,",
                "    pr.chat_log_id,",
                "    pr.user_id,",
                "    pr.username,",
                "    pr.message,",
                "    pr.summary,",
                "    pr.severity,",
                "    pr.status,",
                "    pr.metadata,",
                "    pr.created_at,",
                "    pr.updated_at,",
                "    cl.created_at AS chat_created_at",
                "FROM psych_reports pr",
                "LEFT JOIN chat_logs cl ON cl.id = pr.chat_log_id",
                "WHERE pr.id = %s",
            ]
            params = [report_id]
            if tester_clause:
                query_parts.append(f"  AND {tester_clause}")
                params.extend(tester_params)
            query_parts.append("ORDER BY pr.created_at DESC")
            cur.execute("\n".join(query_parts), tuple(params))
        rows = cur.fetchall()

    records: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        metadata = record.get("metadata")
        if metadata and isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (ValueError, TypeError):
                metadata = {}
            record["metadata"] = metadata
        if not metadata:
            metadata = {}
        message_chunks = metadata.get("message_chunks")
        if isinstance(message_chunks, list) and message_chunks:
            formatted = "\n\n".join(
                chunk.strip()
                for chunk in message_chunks
                if isinstance(chunk, str) and chunk.strip()
            )
            if formatted:
                record["message"] = formatted
        else:
            message_text = record.get("message")
            if isinstance(message_text, str) and message_text:
                record["message"] = (
                    message_text.replace("\r\n", "\n").replace("\r", "\n")
                )
        summary_text = record.get("summary")
        if isinstance(summary_text, str) and summary_text:
            record["summary"] = summary_text.replace("\r\n", "\n").replace("\r", "\n")
        records.append(record)

    return records


def update_psych_report_status(
    report_id: int,
    status: str,
    *,
    updated_by: Optional[str] = None,
) -> bool:
    """Update status (and optionally last_updated_by inside metadata) for a psych report."""
    normalized = (status or "").strip().lower()
    if normalized not in PSYCH_STATUSES:
        raise ValueError(f"Status laporan konseling tidak dikenal: {status}")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT metadata FROM psych_reports WHERE id = %s FOR UPDATE",
            (report_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        metadata = dict(row["metadata"] or {})
        metadata_changed = False
        if updated_by:
            if metadata.get("last_updated_by") != updated_by:
                metadata["last_updated_by"] = updated_by
                metadata_changed = True

        metadata_param = Json(metadata) if metadata_changed else row["metadata"]

        cur.execute(
            """
            UPDATE psych_reports
            SET status = %s,
                metadata = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (normalized, metadata_param, report_id),
        )
        return cur.rowcount > 0

def bulk_update_psych_report_status(
    report_ids: List[int],
    status: str,
    updated_by: Optional[str] = None,
) -> bool:
    """Update the status for a list of psych reports, archiving all reports from the same user if one is archived."""
    if not report_ids:
        return False

    normalized_status = status.lower()
    if normalized_status not in PSYCH_STATUSES and normalized_status != "undo":
        raise ValueError(f"Invalid psych report status: {status}")

    target_status = "open" if normalized_status == "undo" else normalized_status

    with get_cursor(commit=True) as cur:
        # Get the user_ids for the given report_ids
        cur.execute(
            "SELECT DISTINCT user_id FROM psych_reports WHERE id = ANY(%s::int[]) AND user_id IS NOT NULL",
            (report_ids,),
        )
        user_ids = [row[0] for row in cur.fetchall()]

        if not user_ids:
            # If no user_ids are found, just update the selected reports
            cur.execute(
                """
                UPDATE psych_reports
                SET status = %s,
                    updated_at = NOW()
                WHERE id = ANY(%s::int[])
                """,
                (target_status, report_ids),
            )
            return cur.rowcount > 0

        # Update all reports for the found user_ids
        cur.execute(
            """
            UPDATE psych_reports
            SET status = %s,
                updated_at = NOW()
            WHERE user_id = ANY(%s::int[])
            """,
            (target_status, user_ids),
        )
        return cur.rowcount > 0


def update_bullying_report_status(
    report_id: int,
    status: Optional[str] = None,
    *,
    notes: Optional[str] = None,
    updated_by: Optional[str] = None,
    assigned_to: Optional[str] = None,
    due_at: Optional[datetime] = None,
    escalated: Optional[bool] = None,
) -> bool:
    """Update bullying report fields and append an audit trail entry."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT status, notes, assigned_to, due_at, escalated
            FROM bullying_reports
            WHERE id = %s
            FOR UPDATE
            """,
            (report_id,),
        )
        row = cur.fetchone()
        if not row:
            return False

        current = dict(row)
        updates: List[str] = []
        params: List[Any] = []
        changes: Dict[str, Any] = {}

        new_status = current.get("status")
        if status is not None:
            normalized = status.lower()
            if normalized not in BULLYING_STATUSES:
                raise ValueError(f"Status bullying tidak dikenal: {status}")
            if normalized != current.get("status"):
                new_status = normalized
                updates.append("status = %s")
                params.append(normalized)
                if normalized == "resolved":
                    updates.append("resolved_at = NOW()")
                else:
                    updates.append("resolved_at = NULL")
                changes["status"] = {"from": current.get("status"), "to": normalized}

        trimmed_notes = None
        if notes is not None:
            trimmed_notes = notes.strip() or None
            if trimmed_notes != current.get("notes"):
                updates.append("notes = %s")
                params.append(trimmed_notes)
                changes["notes"] = {"from": current.get("notes"), "to": trimmed_notes}

        assigned_clean = (assigned_to or '').strip() or None
        if assigned_to is not None and assigned_clean != current.get("assigned_to"):
            updates.append("assigned_to = %s")
            params.append(assigned_clean)
            changes["assigned_to"] = {"from": current.get("assigned_to"), "to": assigned_clean}

        due_value = None
        if due_at is not None:
            due_value = due_at
            if isinstance(due_at, str):
                due_at_str = due_at.strip()
                due_value = datetime.fromisoformat(due_at_str) if due_at_str else None
            if due_value != current.get("due_at"):
                updates.append("due_at = %s")
                params.append(due_value)
                changes["due_at"] = {
                    "from": current.get("due_at").isoformat() if current.get("due_at") else None,
                    "to": due_value.isoformat() if due_value else None,
                }

        if escalated is not None:
            escalated_bool = bool(escalated)
            if escalated_bool != bool(current.get("escalated")):
                updates.append("escalated = %s")
                params.append(escalated_bool)
                changes["escalated"] = {
                    "from": bool(current.get("escalated")),
                    "to": escalated_bool,
                }
                if escalated_bool:
                    updates.append("priority = TRUE")

        if updated_by is not None:
            updates.append("last_updated_by = %s")
            params.append(updated_by)

        if not updates:
            return False

        updates.append("updated_at = NOW()")
        query = "UPDATE bullying_reports SET " + ", ".join(updates) + " WHERE id = %s"
        cur.execute(query, (*params, report_id))
        if cur.rowcount == 0:
            return False

        event_type = "update"
        if "status" in changes:
            new_state = changes["status"]["to"]
            old_state = changes["status"]["from"]
            if new_state == "resolved":
                event_type = "resolved"
            elif new_state == "pending" and old_state and old_state != "pending":
                event_type = "reopened"
            else:
                event_type = "status_changed"
        elif "escalated" in changes and changes["escalated"]["to"]:
            event_type = "escalated"

        payload: Dict[str, Any] = {"changes": changes}
        if trimmed_notes is not None:
            payload["notes"] = trimmed_notes
        _insert_event = """
            INSERT INTO bullying_report_events (report_id, event_type, actor, payload)
            VALUES (%s, %s, %s, %s)
        """
        cur.execute(_insert_event, (report_id, event_type, updated_by, Json(payload)))
    return True

def bulk_update_bullying_report_status(
    report_ids: List[int],
    status: str,
    updated_by: Optional[str] = None,
) -> bool:
    """Update the status for a list of bullying reports."""
    if not report_ids:
        return False

    normalized_status = status.lower()
    if normalized_status not in BULLYING_STATUSES and normalized_status != "undo":
        raise ValueError(f"Invalid bullying report status: {status}")

    target_status = "pending" if normalized_status == "undo" else normalized_status

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE bullying_reports
            SET status = %s,
                last_updated_by = %s,
                updated_at = NOW()
            WHERE id = ANY(%s::int[])
            """,
            (target_status, updated_by, report_ids),
        )
        return cur.rowcount > 0


def fetch_bullying_report_detail(report_id: int) -> Optional[Dict[str, Any]]:
    tester_clause, tester_params = _tester_condition("br.user_id")
    with get_cursor() as cur:
        query_parts = [
            "SELECT",
            "    br.id,",
            "    br.chat_log_id,",
            "    br.user_id,",
            "    br.username,",
            "    br.description,",
            "    br.status,",
            "    br.priority,",
            "    br.notes,",
            "    br.created_at,",
            "    br.updated_at,",
            "    br.last_updated_by,",
            "    br.category,",
            "    br.severity,",
            "    br.metadata,",
            "    br.assigned_to,",
            "    br.due_at,",
            "    br.resolved_at,",
            "    br.escalated,",
            "    cl.created_at AS chat_created_at",
            "FROM bullying_reports br",
            "LEFT JOIN chat_logs cl ON cl.id = br.chat_log_id",
            "WHERE br.id = %s",
        ]
        params: List[Any] = [report_id]
        if tester_clause:
            query_parts.append(f"  AND {tester_clause}")
            params.extend(tester_params)
        query_parts.append("LIMIT 1")
        cur.execute("\n".join(query_parts), tuple(params))
        report_row = cur.fetchone()
        if not report_row:
            return None
        report = dict(report_row)

        cur.execute(
            """
            SELECT id, event_type, actor, payload, created_at
            FROM bullying_report_events
            WHERE report_id = %s
            ORDER BY created_at ASC
            """,
            (report_id,)
        )
        events = [dict(evt) for evt in cur.fetchall()]
        report["events"] = events
    return report


def fetch_bullying_report_basic(report_id: int) -> Optional[Dict[str, Any]]:
    clause, clause_params = _tester_condition("user_id")
    query = [
        "SELECT id, status, notes, assigned_to, due_at, escalated",
        "FROM bullying_reports",
        "WHERE id = %s",
    ]
    params: List[Any] = [report_id]
    if clause:
        query.append(f"  AND {clause}")
        params.extend(clause_params)
    query.append("LIMIT 1")
    with get_cursor() as cur:
        cur.execute("\n".join(query), tuple(params))
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_corruption_summary() -> Dict[str, int]:
    """Return aggregated counts of corruption reports by status."""
    summary = {status: 0 for status in CORRUPTION_STATUSES}
    total = 0
    clause, clause_params = _tester_condition("user_id")
    with get_cursor() as cur:
        query_parts = [
            "SELECT status, COUNT(*) AS total",
            "FROM corruption_reports",
        ]
        if clause:
            query_parts.append(f"WHERE {clause}")
        query_parts.append("GROUP BY status")
        cur.execute("\n".join(query_parts), tuple(clause_params))
        rows = cur.fetchall()
    for row in rows:
        status = (row.get('status') or '').lower()
        count = int(row.get('total') or 0)
        if status in summary:
            summary[status] = count
            total += count
    summary['total'] = total
    return summary


def fetch_pending_corruption_count() -> int:
    """Shortcut to obtain the number of open corruption reports."""
    return fetch_corruption_summary().get('open', 0)


def fetch_corruption_reports(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated corruption reports ordered by recency."""
    status_filter = None
    if status:
        normalized = status.lower()
        if normalized not in CORRUPTION_STATUSES:
            raise ValueError(f"Status korupsi tidak dikenal: {status}")
        status_filter = normalized

    conditions: List[str] = []
    params: List[Any] = []
    if status_filter:
        conditions.append('status = %s')
        params.append(status_filter)
    tester_clause, tester_params = _tester_condition("user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = ''
    if conditions:
        where_clause = ' WHERE ' + ' AND '.join(conditions)

    query = (
        """
        SELECT
            id,
            ticket_id,
            user_id,
            status,
            involved,
            location,
            time,
            chronology,
            created_at,
            updated_at
        FROM corruption_reports
        """
        + where_clause
        + " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )

    with get_cursor() as cur:
        cur.execute(query, (*params, limit, offset))
        rows = cur.fetchall()
        cur.execute(
            "SELECT COUNT(*) FROM corruption_reports" + where_clause,
            params,
        )
        total = cur.fetchone()[0]

    return [dict(row) for row in rows], int(total or 0)


def fetch_corruption_report_detail(report_id: int) -> Optional[Dict[str, Any]]:
    """Fetches all details for a single corruption report."""
    clause, clause_params = _tester_condition("user_id")
    with get_cursor() as cur:
        query_parts = [
            "SELECT",
            "    id,",
            "    ticket_id,",
            "    user_id,",
            "    status,",
            "    involved,",
            "    location,",
            "    time,",
            "    chronology,",
            "    created_at,",
            "    updated_at",
            "FROM corruption_reports",
            "WHERE id = %s",
        ]
        params: List[Any] = [report_id]
        if clause:
            query_parts.append(f"  AND {clause}")
            params.extend(clause_params)
        query_parts.append("LIMIT 1")
        cur.execute("\n".join(query_parts), tuple(params))
        row = cur.fetchone()
        if not row:
            return None
        
        report = dict(row)
        username = None

        if report.get('user_id'):
            cur.execute(
                "SELECT username FROM chat_logs WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (report['user_id'],)
            )
            user_row = cur.fetchone()
            if user_row:
                username = user_row['username']
        
        report['username'] = username
        report['notes'] = None
        report['assigned_to'] = None
        report['due_at'] = None
        report['resolved_at'] = None
        report['escalated'] = False
        report['last_updated_by'] = None
        report['events'] = []

    return report


def bulk_update_corruption_report_status(
    report_ids: List[int],
    status: str,
    updated_by: Optional[str] = None,
) -> bool:
    """Update the status for a list of corruption reports."""
    if not report_ids:
        return False

    normalized_status = status.lower()
    if normalized_status not in CORRUPTION_STATUSES and normalized_status != "undo":
        raise ValueError(f"Invalid corruption report status: {status}")

    target_status = "open" if normalized_status == "undo" else normalized_status

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE corruption_reports
            SET status = %s,
                updated_at = NOW()
            WHERE id = ANY(%s::int[])
            """,
            (target_status, report_ids),
        )
        return cur.rowcount > 0


def update_corruption_report_status(
    report_id: int,
    status: Optional[str] = None,
    *,
    updated_by: Optional[str] = None,
) -> bool:
    """Update corruption report status."""
    if status is None:
        return False
        
    normalized = status.lower()
    if normalized not in CORRUPTION_STATUSES:
        raise ValueError(f"Status korupsi tidak dikenal: {status}")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE corruption_reports 
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (normalized, report_id)
        )
        return cur.rowcount > 0


def get_user_by_email(email: str) -> Optional[DictRow]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                full_name,
                role,
                nrk,
                nip,
                jabatan,
                degree_prefix,
                degree_suffix,
                no_tester_enabled,
                assigned_class_id,
                last_login_at,
                COALESCE(account_status, 'approved') AS account_status
            FROM dashboard_users
            WHERE email = %s
            LIMIT 1
            """,
            (email,)
        )
        row = cur.fetchone()
    return row

def list_dashboard_users() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.id,
                u.email,
                u.full_name,
                u.role,
                u.nrk,
                u.nip,
                u.jabatan,
                u.degree_prefix,
                u.degree_suffix,
                u.no_tester_enabled,
                u.assigned_class_id,
                u.school_id,
                u.created_at,
                u.last_login_at,
                u.account_status,
                u.merged_to,
                u.merged_at,
                u.whatsapp_number,
                u.requested_kecamatan,
                u.verification_notes,
                k.name as kecamatan_name,
                s.npsn as school_npsn,
                s.name as school_name,
                s.jenjang as school_jenjang,
                sk.name as school_kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            LEFT JOIN portal_schools s ON u.school_id = s.id
            LEFT JOIN portal_kelurahan sl ON s.kelurahan_id = sl.id
            LEFT JOIN portal_kecamatan sk ON sl.kecamatan_id = sk.id
            ORDER BY u.created_at DESC
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def update_dashboard_user(
    user_id: int,
    full_name: str,
    role: str,
    email: Optional[str] = None,
    password_hash: Optional[str] = None,
    account_status: Optional[str] = None,
    school_id: Optional[int] = None,
    requested_kecamatan: object = _UNSET,
    jabatan: Optional[str] = None,
    whatsapp_number: Optional[str] = None,
    nip: Optional[str] = None,
    nrk: Optional[str] = None,
    degree_prefix: Optional[str] = None,
    degree_suffix: Optional[str] = None,
) -> bool:
    """Update an existing dashboard user."""
    updates = [
        "full_name = %s",
        "role = %s",
        "updated_at = NOW()"  # Assuming updated_at exists or handled by DB trigger? If not, ignore
    ]
    params = [full_name, role]
    
    if email:
        updates.append("email = %s")
        params.append(email)
        
    if password_hash:
        updates.append("password_hash = %s")
        params.append(password_hash)
        
    if account_status:
        updates.append("account_status = %s")
        params.append(account_status)

    if jabatan is not None:
        updates.append("jabatan = %s")
        params.append(jabatan)

    if whatsapp_number is not None:
        updates.append("whatsapp_number = %s")
        params.append(whatsapp_number)

    if nip is not None:
        updates.append("nip = %s")
        params.append(nip)

    if nrk is not None:
        updates.append("nrk = %s")
        params.append(nrk)

    if degree_prefix is not None:
        updates.append("degree_prefix = %s")
        params.append(degree_prefix)

    if degree_suffix is not None:
        updates.append("degree_suffix = %s")
        params.append(degree_suffix)

    if school_id is not None:
        updates.append("school_id = %s")
        params.append(school_id)

    if requested_kecamatan is not _UNSET:
        updates.append("requested_kecamatan = %s")
        params.append(requested_kecamatan)
        
    # check for updated_at column or just ignore it for now if unsure
    # Safer to check schema first? Or just try basic updates
    # Let's remove updated_at from list to be safe as it wasn't in original schema view
    updates = [u for u in updates if "updated_at" not in u]
        
    query = f"UPDATE dashboard_users SET {', '.join(updates)} WHERE id = %s"
    params.append(user_id)
    
    with get_cursor(commit=True) as cur:
        cur.execute(query, params)
        return cur.rowcount > 0


def create_dashboard_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str = "viewer",
    school_id: Optional[int] = None,
    requested_kecamatan: Optional[int] = None,
    *,
    nrk: Optional[str] = None,
    nip: Optional[str] = None,
    jabatan: Optional[str] = None,
    degree_prefix: Optional[str] = None,
    degree_suffix: Optional[str] = None,
    account_status: Optional[str] = None,
) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO dashboard_users (
                email,
                full_name,
                password_hash,
                role,
                school_id,
                requested_kecamatan,
                nrk,
                nip,
                jabatan,
                degree_prefix,
                degree_suffix,
                account_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                email,
                full_name,
                password_hash,
                role,
                school_id,
                requested_kecamatan,
                nrk,
                nip,
                jabatan,
                degree_prefix,
                degree_suffix,
                account_status or "approved",
            ),
        )
        new_id = cur.fetchone()[0]
    return int(new_id)


def list_admin_users() -> List[Dict[str, Any]]:
    """List dashboard users with admin role."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, email, role
            FROM dashboard_users
            WHERE role = 'admin'
            ORDER BY full_name ASC
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_telegram_notification_settings() -> Dict[str, Any]:
    """Fetch stored Telegram bot token configuration."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.bot_token,
                    s.updated_at,
                    s.updated_by,
                    u.full_name AS updated_by_name,
                    u.email AS updated_by_email
                FROM telegram_notification_settings s
                LEFT JOIN dashboard_users u ON u.id = s.updated_by
                WHERE s.id = 1
                LIMIT 1
                """
            )
            row = cur.fetchone()
    except Exception:
        return {}
    return dict(row) if row else {}


def upsert_telegram_notification_settings(bot_token: Optional[str], updated_by: Optional[int]) -> bool:
    """Insert/update Telegram bot token configuration."""
    clean_token = (bot_token or "").strip() or None
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO telegram_notification_settings (id, bot_token, updated_at, updated_by)
            VALUES (1, %s, NOW(), %s)
            ON CONFLICT (id) DO UPDATE
            SET bot_token = EXCLUDED.bot_token,
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            """,
            (clean_token, updated_by),
        )
        return True


def list_telegram_admin_accounts() -> List[Dict[str, Any]]:
    """List Telegram admin username mappings."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ta.id,
                ta.telegram_username,
                ta.dashboard_user_id,
                ta.created_at,
                u.full_name AS admin_name,
                u.email AS admin_email,
                u.role AS admin_role
            FROM telegram_admin_accounts ta
            LEFT JOIN dashboard_users u ON u.id = ta.dashboard_user_id
            ORDER BY LOWER(ta.telegram_username) ASC
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def list_telegram_notification_groups() -> List[Dict[str, Any]]:
    """List Telegram group chat IDs for notifications."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                tg.id,
                tg.chat_id,
                tg.title,
                tg.created_at,
                tg.updated_at,
                tg.created_by,
                u.full_name AS created_by_name,
                u.email AS created_by_email
            FROM telegram_notification_groups tg
            LEFT JOIN dashboard_users u ON u.id = tg.created_by
            ORDER BY tg.updated_at DESC
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def upsert_telegram_notification_group(chat_id: int, title: Optional[str], created_by: Optional[int]) -> bool:
    """Insert or update a Telegram notification group."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO telegram_notification_groups (chat_id, title, created_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE
            SET title = EXCLUDED.title,
                created_by = EXCLUDED.created_by,
                updated_at = NOW()
            """,
            (chat_id, title, created_by),
        )
        return True


def delete_telegram_notification_group(group_id: int) -> bool:
    """Delete Telegram notification group by id."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM telegram_notification_groups WHERE id = %s", (group_id,))
        return cur.rowcount > 0


def delete_telegram_notification_group_by_chat_id(chat_id: int) -> bool:
    """Delete Telegram notification group by chat id."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM telegram_notification_groups WHERE chat_id = %s", (chat_id,))
        return cur.rowcount > 0


def upsert_telegram_admin_accounts(entries: List[Dict[str, Any]], created_by: Optional[int]) -> int:
    """Upsert multiple Telegram admin mappings."""
    if not entries:
        return 0
    with get_cursor(commit=True) as cur:
        for entry in entries:
            cur.execute(
                """
                INSERT INTO telegram_admin_accounts (dashboard_user_id, telegram_username, created_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_username) DO UPDATE
                SET dashboard_user_id = EXCLUDED.dashboard_user_id,
                    created_by = EXCLUDED.created_by
                """,
                (
                    entry.get("dashboard_user_id"),
                    entry.get("telegram_username"),
                    created_by,
                ),
            )
    return len(entries)


def delete_telegram_admin_account(mapping_id: int) -> bool:
    """Delete a Telegram admin mapping by id."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM telegram_admin_accounts WHERE id = %s", (mapping_id,))
        return cur.rowcount > 0


def get_telegram_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Return admin mapping if username is authorized and linked to admin user."""
    if not username:
        return None
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        return None
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                ta.id,
                ta.telegram_username,
                ta.dashboard_user_id,
                u.full_name AS admin_name,
                u.email AS admin_email
            FROM telegram_admin_accounts ta
            JOIN dashboard_users u ON u.id = ta.dashboard_user_id
            WHERE ta.telegram_username = %s
              AND u.role = 'admin'
            LIMIT 1
            """,
            (normalized,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_pending_dashboard_users(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch pending dashboard user registrations."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.role,
                u.created_at,
                k.name AS kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            WHERE u.account_status = 'pending'
            ORDER BY u.created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_dashboard_user_basic(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch basic dashboard user details for verification."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                full_name,
                email,
                role,
                account_status,
                requested_kecamatan,
                created_at
            FROM dashboard_users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def update_dashboard_user_verification(
    user_id: int,
    status: str,
    verified_by: Optional[int],
    note: Optional[str] = None,
) -> bool:
    """Update account_status for dashboard user verification."""
    normalized = (status or "").strip().lower()
    if normalized not in {"pending", "approved", "rejected", "suspended"}:
        raise ValueError("Status verifikasi tidak dikenal.")
    clean_note = (note or "").strip() or None
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE dashboard_users
            SET account_status = %s,
                verification_notes = COALESCE(%s, verification_notes),
                verified_by = CASE WHEN %s IN ('approved', 'rejected') THEN %s ELSE NULL END,
                verified_at = CASE WHEN %s IN ('approved', 'rejected') THEN NOW() ELSE NULL END
            WHERE id = %s
            """,
            (normalized, clean_note, normalized, verified_by, normalized, user_id),
        )
        return cur.rowcount > 0


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _list_user_fk_columns(cur) -> List[Tuple[str, str]]:
    cur.execute(
        """
        SELECT
            tc.table_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND ccu.table_name = 'dashboard_users'
          AND ccu.column_name = 'id'
        ORDER BY tc.table_name, kcu.column_name
        """
    )
    return [(row["table_name"], row["column_name"]) for row in cur.fetchall()]


def _list_unique_constraints(cur, table_name: str) -> List[List[str]]:
    cur.execute(
        """
        SELECT
            tc.constraint_name,
            ARRAY_AGG(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'UNIQUE'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
        GROUP BY tc.constraint_name
        """,
        (table_name,),
    )
    return [list(row["columns"]) for row in cur.fetchall()]


def merge_dashboard_users(old_user_id: int, new_user_id: int, merged_by: Optional[int] = None) -> Dict[str, Any]:
    """Merge two dashboard user accounts by moving all references to new_user_id."""
    if old_user_id == new_user_id:
        raise ValueError("User lama dan baru tidak boleh sama.")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            SELECT id, full_name, email, account_status
            FROM dashboard_users
            WHERE id IN (%s, %s)
            """,
            (old_user_id, new_user_id),
        )
        rows = {int(row["id"]): dict(row) for row in cur.fetchall()}
        if old_user_id not in rows or new_user_id not in rows:
            raise ValueError("User tidak ditemukan.")

        fk_columns = _list_user_fk_columns(cur)
        for table_name, column_name in fk_columns:
            if table_name == "dashboard_users" and column_name == "id":
                continue

            unique_constraints = _list_unique_constraints(cur, table_name)
            for columns in unique_constraints:
                if column_name not in columns:
                    continue
                other_cols = [col for col in columns if col != column_name]
                if other_cols:
                    comparisons = " AND ".join(
                        f"t_old.{_quote_ident(col)} IS NOT DISTINCT FROM t_new.{_quote_ident(col)}"
                        for col in other_cols
                    )
                else:
                    comparisons = "TRUE"

                delete_sql = (
                    f"DELETE FROM {_quote_ident(table_name)} t_old "
                    f"USING {_quote_ident(table_name)} t_new "
                    f"WHERE t_old.{_quote_ident(column_name)} = %s "
                    f"AND t_new.{_quote_ident(column_name)} = %s "
                    f"AND {comparisons}"
                )
                cur.execute(delete_sql, (old_user_id, new_user_id))

            update_sql = (
                f"UPDATE {_quote_ident(table_name)} "
                f"SET {_quote_ident(column_name)} = %s "
                f"WHERE {_quote_ident(column_name)} = %s"
            )
            cur.execute(update_sql, (new_user_id, old_user_id))

        # Disable old user and mark merge target
        cur.execute(
            """
            UPDATE dashboard_users
            SET account_status = 'disabled',
                merged_to = %s,
                merged_at = NOW()
            WHERE id = %s
            """,
            (new_user_id, old_user_id),
        )

    return {"old_user": rows.get(old_user_id), "new_user": rows.get(new_user_id), "merged_by": merged_by}


# =====================================================
# Monev Team Management
# =====================================================

def get_monev_teams(team_type: str = None) -> List[Dict[str, Any]]:
    """Get all monev teams with kecamatan and coordinator info.
    
    Args:
        team_type: Optional filter - 'kasi' or 'kecamatan'. None returns all.
    """
    with get_cursor() as cur:
        query = """
            SELECT 
                mt.id,
                mt.kecamatan_id,
                mt.coordinator_id,
                mt.name,
                mt.notes,
                mt.team_type,
                mt.created_at,
                mt.updated_at,
                k.name as kecamatan_name,
                u.full_name as coordinator_name,
                u.role as coordinator_role
            FROM monev_teams mt
            LEFT JOIN portal_kecamatan k ON mt.kecamatan_id = k.id
            LEFT JOIN dashboard_users u ON mt.coordinator_id = u.id
        """
        if team_type:
            query += " WHERE mt.team_type = %s"
            query += " ORDER BY mt.name"
            cur.execute(query, (team_type,))
        else:
            query += " ORDER BY mt.team_type, mt.name"
            cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def create_monev_team(name: str, team_type: str, kecamatan_id: int = None) -> Optional[int]:
    """Create a new monev team.
    
    Args:
        name: Team name
        team_type: Type - 'kasi', 'kecamatan', or 'custom'
        kecamatan_id: Optional kecamatan ID (for kecamatan type teams)
    
    Returns:
        New team ID if successful, None otherwise
    """
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO monev_teams (name, team_type, kecamatan_id, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            RETURNING id
        """, (name, team_type, kecamatan_id))
        row = cur.fetchone()
        return row['id'] if row else None


def delete_monev_team(team_id: int) -> bool:
    """Delete a monev team and its members.
    
    Args:
        team_id: ID of team to delete
    
    Returns:
        True if deleted, False otherwise
    """
    with get_cursor(commit=True) as cur:
        # First delete all team members
        cur.execute("DELETE FROM monev_team_members WHERE team_id = %s", (team_id,))
        # Then delete the team
        cur.execute("DELETE FROM monev_teams WHERE id = %s", (team_id,))
        return cur.rowcount > 0


def get_monev_team_by_kecamatan(kecamatan_id: int) -> Optional[Dict[str, Any]]:
    """Get monev team for a specific kecamatan."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT 
                mt.id,
                mt.kecamatan_id,
                mt.coordinator_id,
                mt.name,
                mt.notes,
                mt.created_at,
                mt.updated_at,
                k.name as kecamatan_name,
                u.full_name as coordinator_name,
                u.role as coordinator_role
            FROM monev_teams mt
            JOIN portal_kecamatan k ON mt.kecamatan_id = k.id
            LEFT JOIN dashboard_users u ON mt.coordinator_id = u.id
            WHERE mt.kecamatan_id = %s
        """, (kecamatan_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_team_members(team_id: int) -> List[Dict[str, Any]]:
    """Get all members of a monev team."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT 
                mtm.id,
                mtm.team_id,
                mtm.staff_id,
                mtm.added_at,
                u.full_name,
                u.email,
                u.role,
                u.nip,
                u.jabatan
            FROM monev_team_members mtm
            JOIN dashboard_users u ON mtm.staff_id = u.id
            WHERE mtm.team_id = %s
            ORDER BY mtm.added_at
        """, (team_id,))
        return [dict(row) for row in cur.fetchall()]


def update_team_coordinator(team_id: int, coordinator_id: Optional[int]) -> bool:
    """Update the coordinator for a monev team."""
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE monev_teams 
            SET coordinator_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (coordinator_id, team_id))
        return cur.rowcount > 0


def add_team_member(team_id: int, staff_id: int, added_by: Optional[int] = None) -> bool:
    """Add a member to a monev team."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO monev_team_members (team_id, staff_id, added_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (team_id, staff_id) DO NOTHING
            """, (team_id, staff_id, added_by))
            return cur.rowcount > 0
    except Exception:
        return False


def remove_team_member(member_id: int) -> bool:
    """Remove a member from a monev team."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_team_members WHERE id = %s", (member_id,))
        return cur.rowcount > 0


def get_available_staff() -> List[Dict[str, Any]]:
    """Get staff users who can be assigned to teams (coordinator or staff role)."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT 
                id,
                full_name,
                email,
                role,
                nip,
                jabatan
            FROM dashboard_users
            WHERE role IN ('coordinator', 'staff', 'admin')
              AND account_status = 'approved'
            ORDER BY full_name
        """)
        return [dict(row) for row in cur.fetchall()]

def create_team_member_request(
    team_id: int,
    staff_id: int,
    requested_by: int,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a join request for adding a staff to a team.
    
    Returns dict with 'status' = created|pending|already_member and optional request data.
    """
    with get_cursor(commit=True) as cur:
        # Already a member?
        cur.execute(
            "SELECT 1 FROM monev_team_members WHERE team_id = %s AND staff_id = %s",
            (team_id, staff_id),
        )
        if cur.fetchone():
            return {"status": "already_member"}
        
        # Existing pending request?
        cur.execute(
            """
            SELECT id, status, created_at
            FROM monev_team_member_requests
            WHERE team_id = %s AND staff_id = %s AND status = 'pending'
            """,
            (team_id, staff_id),
        )
        pending = cur.fetchone()
        if pending:
            return {"status": "pending", "request": dict(pending)}
        
        # Insert new request
        cur.execute(
            """
            INSERT INTO monev_team_member_requests (team_id, staff_id, requested_by, note)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (team_id, staff_id, requested_by, note),
        )
        row = cur.fetchone()
        return {"status": "created", "request": dict(row)}


def list_team_member_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List member requests, optionally filtered by status."""
    conditions = []
    params: List[Any] = []
    if status:
        conditions.append("r.status = %s")
        params.append(status)
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT 
            r.*,
            t.name as team_name,
            t.team_type,
            u.full_name as staff_name,
            u.email as staff_email,
            rb.full_name as requested_by_name,
            rv.full_name as reviewed_by_name
        FROM monev_team_member_requests r
        JOIN monev_teams t ON r.team_id = t.id
        JOIN dashboard_users u ON r.staff_id = u.id
        JOIN dashboard_users rb ON r.requested_by = rb.id
        LEFT JOIN dashboard_users rv ON r.reviewed_by = rv.id
        {where_clause}
        ORDER BY r.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def list_team_member_requests_for_team(
    team_id: int,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List requests for a specific team."""
    conditions = ["r.team_id = %s"]
    params: List[Any] = [team_id]
    if status:
        conditions.append("r.status = %s")
        params.append(status)
    where_clause = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT 
            r.*,
            u.full_name as staff_name,
            u.email as staff_email,
            rb.full_name as requested_by_name,
            rv.full_name as reviewed_by_name
        FROM monev_team_member_requests r
        JOIN dashboard_users u ON r.staff_id = u.id
        JOIN dashboard_users rb ON r.requested_by = rb.id
        LEFT JOIN dashboard_users rv ON r.reviewed_by = rv.id
        {where_clause}
        ORDER BY r.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_team_member_request(request_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single team member request."""
    query = """
        SELECT 
            r.*,
            t.name as team_name,
            u.full_name as staff_name,
            rb.full_name as requested_by_name,
            rv.full_name as reviewed_by_name
        FROM monev_team_member_requests r
        JOIN monev_teams t ON r.team_id = t.id
        JOIN dashboard_users u ON r.staff_id = u.id
        JOIN dashboard_users rb ON r.requested_by = rb.id
        LEFT JOIN dashboard_users rv ON r.reviewed_by = rv.id
        WHERE r.id = %s
    """
    with get_cursor() as cur:
        cur.execute(query, (request_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_team_member_request_status(
    request_id: int,
    status: str,
    reviewed_by: int,
    reviewer_note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update request status and return updated row."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_team_member_requests
            SET status = %s,
                reviewed_by = %s,
                reviewer_note = %s,
                reviewed_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (status, reviewed_by, reviewer_note, request_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_dashboard_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str,
    *,
    nrk: Optional[str] = None,
    nip: Optional[str] = None,
    jabatan: Optional[str] = None,
    degree_prefix: Optional[str] = None,
    degree_suffix: Optional[str] = None,
) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO dashboard_users (email, full_name, password_hash, role, nrk, nip, jabatan, degree_prefix, degree_suffix)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    nrk = EXCLUDED.nrk,
                    nip = EXCLUDED.nip,
                    jabatan = EXCLUDED.jabatan,
                    degree_prefix = EXCLUDED.degree_prefix,
                    degree_suffix = EXCLUDED.degree_suffix,
                    last_login_at = dashboard_users.last_login_at
            RETURNING id
            """,
            (email, full_name, password_hash, role, nrk, nip, jabatan, degree_prefix, degree_suffix),
        )
        row = cur.fetchone()
    return int(row[0])

def update_last_login(user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE dashboard_users SET last_login_at = NOW() WHERE id = %s",
            (user_id,),
        )


def update_no_tester_preference(user_id: int, enabled: bool) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE dashboard_users SET no_tester_enabled = %s WHERE id = %s",
            (enabled, user_id),
        )
        return cur.rowcount > 0


def _normalize_status_filter(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in ACCOUNT_STATUS_CHOICES else None


def fetch_aska_users(source: str, status: Optional[str], search: Optional[str], *, limit: int = 200) -> List[Dict[str, Any]]:
    """Gabungkan daftar user web & Telegram sesuai filter."""
    normalized_source = (source or "web").strip().lower()
    normalized_status = _normalize_status_filter(status)
    normalized_search = (search or "").strip()

    rows: List[Dict[str, Any]] = []
    fetch_web = normalized_source in {"web", "all"}
    fetch_telegram = normalized_source in {"telegram", "all"}

    if fetch_web:
        conditions: List[str] = []
        params: List[Any] = []
        if normalized_status:
            conditions.append("status = %s")
            params.append(normalized_status)
        if normalized_search:
            conditions.append("(email ILIKE %s OR full_name ILIKE %s)")
            term = f"%{normalized_search}%"
            params.extend([term, term])
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                id,
                full_name,
                email,
                access_tier,
                last_login,
                created_at,
                status,
                status_reason,
                status_changed_at,
                status_changed_by
            FROM web_users
            {where_clause}
            ORDER BY COALESCE(last_login, created_at) DESC
            LIMIT %s
        """
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                rows.append(
                    {
                        "channel": "web",
                        "id": row["id"],
                        "display_name": row["full_name"],
                        "identifier": row["email"],
                        "status": row["status"],
                        "status_reason": row["status_reason"],
                        "status_changed_at": row["status_changed_at"],
                        "status_changed_by": row["status_changed_by"],
                        "last_activity": row["last_login"] or row["created_at"],
                        "created_at": row["created_at"],
                        "extra": {"access_tier": row["access_tier"]},
                    }
                )

    if fetch_telegram:
        conditions = []
        params = []
        if normalized_status:
            conditions.append("status = %s")
            params.append(normalized_status)
        if normalized_search:
            conditions.append("(username ILIKE %s OR CAST(telegram_user_id AS TEXT) ILIKE %s)")
            term = f"%{normalized_search}%"
            params.extend([term, term])
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                telegram_user_id,
                username,
                first_seen_at,
                last_seen_at,
                status,
                status_reason,
                status_changed_at,
                status_changed_by,
                last_message_preview
            FROM telegram_users
            {where_clause}
            ORDER BY COALESCE(last_seen_at, first_seen_at) DESC
            LIMIT %s
        """
        params.append(limit)
        with get_cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                rows.append(
                    {
                        "channel": "telegram",
                        "id": row["telegram_user_id"],
                        "display_name": row["username"] or f"ID {row['telegram_user_id']}",
                        "identifier": f"@{row['username']}" if row["username"] else row["telegram_user_id"],
                        "status": row["status"],
                        "status_reason": row["status_reason"],
                        "status_changed_at": row["status_changed_at"],
                        "status_changed_by": row["status_changed_by"],
                        "last_activity": row["last_seen_at"] or row["first_seen_at"],
                        "created_at": row["first_seen_at"],
                        "extra": {"last_message_preview": row["last_message_preview"]},
                    }
                )

    rows.sort(key=lambda item: item.get("last_activity") or item.get("created_at") or datetime.min, reverse=True)
    return rows[:limit]


def summarize_aska_users() -> Dict[str, Dict[str, int]]:
    """Hitung total user per status untuk web dan Telegram."""
    summary = {
        "web": {status: 0 for status in ACCOUNT_STATUS_CHOICES},
        "telegram": {status: 0 for status in ACCOUNT_STATUS_CHOICES},
    }
    with get_cursor() as cur:
        cur.execute("SELECT status, COUNT(*) FROM web_users GROUP BY status")
        for status, total in cur.fetchall():
            summary["web"][status] = int(total)
        cur.execute("SELECT status, COUNT(*) FROM telegram_users GROUP BY status")
        for status, total in cur.fetchall():
            summary["telegram"][status] = int(total)
    for scope in summary.values():
        scope["total"] = sum(scope.get(status, 0) for status in ACCOUNT_STATUS_CHOICES)
    summary["combined"] = {
        status: summary["web"].get(status, 0) + summary["telegram"].get(status, 0)
        for status in ACCOUNT_STATUS_CHOICES
    }
    summary["combined"]["total"] = summary["web"].get("total", 0) + summary["telegram"].get("total", 0)
    return summary


def update_web_user_status(user_id: int, status: str, reason: Optional[str], *, changed_by: str) -> bool:
    normalized = _normalize_status_filter(status)
    if normalized is None:
        raise ValueError("Status tidak valid.")
    cleaned_reason = (reason or "").strip() or None
    if cleaned_reason:
        cleaned_reason = cleaned_reason[:500]
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE web_users
            SET status = %s,
                status_reason = %s,
                status_changed_at = NOW(),
                status_changed_by = %s
            WHERE id = %s
            """,
            (normalized, cleaned_reason, changed_by, user_id),
        )
        return cur.rowcount > 0


def update_telegram_user_status(user_id: int, status: str, reason: Optional[str], *, changed_by: str) -> bool:
    normalized = _normalize_status_filter(status)
    if normalized is None:
        raise ValueError("Status tidak valid.")
    cleaned_reason = (reason or "").strip() or None
    if cleaned_reason:
        cleaned_reason = cleaned_reason[:500]
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE telegram_users
            SET status = %s,
                status_reason = %s,
                status_changed_at = NOW(),
                status_changed_by = %s
            WHERE telegram_user_id = %s
            """,
            (normalized, cleaned_reason, changed_by, user_id),
        )
        return cur.rowcount > 0


# --- Chat Feedback queries --------------------------------------------------

def fetch_feedback_summary(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """Aggregate feedback summary statistics for a given date range."""
    conditions: List[str] = []
    params: List[Any] = []

    if start_date:
        conditions.append("cf.created_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("cf.created_at <= %s")
        params.append(end_date)

    tester_clause, tester_params = _tester_condition("cf.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT 
                COUNT(*) FILTER (WHERE feedback_type = 'like') as total_likes,
                COUNT(*) FILTER (WHERE feedback_type = 'dislike') as total_dislikes,
                COUNT(*) as total_feedback,
                ROUND(100.0 * COUNT(*) FILTER (WHERE feedback_type = 'like') / NULLIF(COUNT(*), 0), 2) as positive_rate
            FROM chat_feedback cf
            {where_clause}
            """,
            tuple(params),
        )
        row = cur.fetchone()

    return {
        "total_likes": int(row["total_likes"] or 0),
        "total_dislikes": int(row["total_dislikes"] or 0),
        "total_feedback": int(row["total_feedback"] or 0),
        "positive_rate": float(row["positive_rate"] or 0.0),
        "period_start": start_date,
        "period_end": end_date,
    }


def fetch_feedback_list(
    filter_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 25,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Get paginated list of feedback with message context."""
    conditions: List[str] = []
    params: List[Any] = []

    if filter_type and filter_type in ("like", "dislike"):
        conditions.append("cf.feedback_type = %s")
        params.append(filter_type)
    if start_date:
        conditions.append("cf.created_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("cf.created_at <= %s")
        params.append(end_date)

    tester_clause, tester_params = _tester_condition("cf.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT 
                cf.id,
                cf.chat_log_id,
                cf.user_id,
                cf.username,
                cf.feedback_type,
                cf.created_at,
                cl.text as message_text,
                cl.created_at as message_created_at
            FROM chat_feedback cf
            JOIN chat_logs cl ON cf.chat_log_id = cl.id
            {where_clause}
            ORDER BY cf.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        )
        rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM chat_feedback cf
            {where_clause}
            """,
            tuple(params),
        )
        total = cur.fetchone()[0]

    return [dict(row) for row in rows], int(total or 0)


def fetch_feedback_trend(start_date: datetime, days: int = 30) -> List[Dict[str, Any]]:
    """Get daily feedback trend for chart visualization."""
    days = max(1, days)
    conditions = ["cf.created_at >= %s"]
    params: List[Any] = [start_date]

    tester_clause, tester_params = _tester_condition("cf.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = f" WHERE {' AND '.join(conditions)}"

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT 
                DATE(cf.created_at) as day,
                COUNT(*) FILTER (WHERE cf.feedback_type = 'like') as likes,
                COUNT(*) FILTER (WHERE cf.feedback_type = 'dislike') as dislikes
            FROM chat_feedback cf
            {where_clause}
            GROUP BY DATE(cf.created_at)
            ORDER BY day ASC
            """,
            tuple(params),
        )
        rows = cur.fetchall()

    return [
        {
            "day": row["day"],
            "likes": int(row["likes"] or 0),
            "dislikes": int(row["dislikes"] or 0),
            "total": int(row["likes"] or 0) + int(row["dislikes"] or 0),
        }
        for row in rows
    ]


def fetch_feedback_by_message(chat_log_id: int) -> Optional[Dict[str, Any]]:
    """Get feedback details for a specific message."""
    conditions = ["cf.chat_log_id = %s"]
    params: List[Any] = [chat_log_id]

    tester_clause, tester_params = _tester_condition("cf.user_id")
    if tester_clause:
        conditions.append(tester_clause)
        params.extend(tester_params)

    where_clause = f" WHERE {' AND '.join(conditions)}"

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT 
                cf.id,
                cf.chat_log_id,
                cf.user_id,
                cf.username,
                cf.feedback_type,
                cf.created_at,
                cf.updated_at,
                cl.text as message_text,
                cl.created_at as message_created_at,
                cl.user_id as message_user_id,
                cl.username as message_username
            FROM chat_feedback cf
            JOIN chat_logs cl ON cf.chat_log_id = cl.id
            {where_clause}
            LIMIT 1
            """,
            tuple(params),
        )
        row = cur.fetchone()

    return dict(row) if row else None
