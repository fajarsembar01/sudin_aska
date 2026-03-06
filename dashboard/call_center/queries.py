"""Database queries for the Call Center module."""

from __future__ import annotations

import os
import traceback
from typing import Optional, List, Dict, Any

from ..db_access import get_cursor


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def upsert_cc_conversation(
    wa_user_id: str,
    display_name: Optional[str] = None,
) -> dict:
    """Create or update a conversation for the given WA user.

    Returns the conversation row as a dict.
    """
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_conversations (wa_user_id, display_name, last_message_at, updated_at)
            VALUES (%(wa)s, %(name)s, NOW(), NOW())
            ON CONFLICT (wa_user_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, cc_conversations.display_name),
                last_message_at = NOW(),
                updated_at = NOW()
            RETURNING id, wa_user_id, display_name, status, last_message_at,
                      unread_count, created_at, updated_at
            """,
            {"wa": wa_user_id, "name": display_name},
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def fetch_cc_conversations(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Return paginated conversations sorted by last_message_at DESC."""
    conditions = []
    params: dict = {}

    if status_filter in ("open", "closed"):
        conditions.append("c.status = %(status)s")
        params["status"] = status_filter

    if search:
        conditions.append(
            "(c.display_name ILIKE %(search)s OR c.wa_user_id ILIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS cnt FROM cc_conversations c {where}", params
        )
        total = (cur.fetchone() or {}).get("cnt", 0)

        cur.execute(
            f"""
            SELECT c.id, c.wa_user_id, c.display_name, c.status,
                   c.last_message_at, c.unread_count, c.created_at, c.updated_at,
                   (SELECT m.message_text FROM cc_messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.created_at DESC LIMIT 1) AS last_message_preview
            FROM cc_conversations c
            {where}
            ORDER BY c.last_message_at DESC NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {**params, "limit": limit, "offset": offset},
        )
        rows = [dict(r) for r in cur.fetchall()]

    return rows, total


def fetch_cc_conversation(conv_id: int) -> Optional[dict]:
    """Fetch a single conversation by ID."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, wa_user_id, display_name, status,
                   last_message_at, unread_count, created_at, updated_at
            FROM cc_conversations WHERE id = %(id)s
            """,
            {"id": conv_id},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def mark_conversation_read(conv_id: int) -> None:
    """Reset unread count to 0."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE cc_conversations SET unread_count = 0, updated_at = NOW() WHERE id = %(id)s",
            {"id": conv_id},
        )


def close_conversation(conv_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE cc_conversations SET status = 'closed', updated_at = NOW() WHERE id = %(id)s",
            {"id": conv_id},
        )


def reopen_conversation(conv_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE cc_conversations SET status = 'open', updated_at = NOW() WHERE id = %(id)s",
            {"id": conv_id},
        )


def fetch_cc_unread_total() -> int:
    """Return total unread messages across all open conversations."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(unread_count), 0) AS total FROM cc_conversations WHERE status = 'open'"
            )
            row = cur.fetchone()
        return int((row or {}).get("total", 0))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def save_cc_message(
    conversation_id: int,
    direction: str,
    message_text: str,
    admin_user_id: Optional[int] = None,
    admin_display_name: Optional[str] = None,
    wa_message_id: Optional[str] = None,
) -> dict:
    """Insert a message and update conversation timestamps/unread."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_messages
                (conversation_id, direction, message_text,
                 admin_user_id, admin_display_name, wa_message_id)
            VALUES (%(conv)s, %(dir)s, %(text)s, %(admin)s, %(admin_name)s, %(wa_msg)s)
            RETURNING id, conversation_id, direction, message_text,
                      admin_user_id, admin_display_name, wa_message_id, created_at
            """,
            {
                "conv": conversation_id,
                "dir": direction,
                "text": message_text,
                "admin": admin_user_id,
                "admin_name": admin_display_name,
                "wa_msg": wa_message_id,
            },
        )
        row = cur.fetchone()

        # Update conversation
        if direction == "inbound":
            cur.execute(
                """
                UPDATE cc_conversations
                SET last_message_at = NOW(),
                    unread_count = unread_count + 1,
                    status = 'open',
                    updated_at = NOW()
                WHERE id = %(conv)s
                """,
                {"conv": conversation_id},
            )
        else:
            cur.execute(
                """
                UPDATE cc_conversations
                SET last_message_at = NOW(), updated_at = NOW()
                WHERE id = %(conv)s
                """,
                {"conv": conversation_id},
            )

    return dict(row) if row else {}


def fetch_cc_messages(
    conversation_id: int,
    limit: int = 200,
    after_id: Optional[int] = None,
) -> list[dict]:
    """Fetch messages for a conversation, optionally only those after a given ID."""
    params: dict = {"conv": conversation_id, "limit": limit}
    after_clause = ""
    if after_id:
        after_clause = "AND m.id > %(after_id)s"
        params["after_id"] = after_id

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT m.id, m.conversation_id, m.direction, m.message_text,
                   m.admin_user_id, m.admin_display_name, m.wa_message_id, m.created_at
            FROM cc_messages m
            WHERE m.conversation_id = %(conv)s {after_clause}
            ORDER BY m.created_at ASC
            LIMIT %(limit)s
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Telegram notification settings (Call Center)
# ---------------------------------------------------------------------------

def upsert_cc_telegram_settings(bot_token: str, updated_by: Optional[int] = None) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_telegram_settings (id, bot_token, updated_by, updated_at)
            VALUES (1, %(token)s, %(by)s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                bot_token = EXCLUDED.bot_token,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            {"token": bot_token.strip() if bot_token else None, "by": updated_by},
        )


def fetch_cc_telegram_settings() -> dict:
    try:
        with get_cursor() as cur:
            cur.execute("SELECT bot_token, updated_at FROM cc_telegram_settings WHERE id = 1")
            row = cur.fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}


def add_cc_telegram_group(chat_id: int, title: Optional[str] = None, created_by: Optional[int] = None) -> bool:
    """Add a Telegram group for CC notifications. Returns True on success."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO cc_telegram_groups (chat_id, title, created_by, updated_at)
                VALUES (%(cid)s, %(title)s, %(by)s, NOW())
                ON CONFLICT (chat_id) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, cc_telegram_groups.title),
                    updated_at = NOW()
                """,
                {"cid": chat_id, "title": title, "by": created_by},
            )
        return True
    except Exception:
        return False


def list_cc_telegram_groups() -> list[dict]:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, chat_id, title, created_at FROM cc_telegram_groups ORDER BY created_at"
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def delete_cc_telegram_group(group_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM cc_telegram_groups WHERE id = %(id)s", {"id": group_id})
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Telegram allowed users (who may receive CC notifications)
# ---------------------------------------------------------------------------

def list_cc_telegram_allowed_users() -> list[dict]:
    """List dashboard users who are allowed to receive CC Telegram notifications."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.user_id, a.created_at,
                       u.full_name, u.email
                FROM cc_telegram_allowed_users a
                JOIN dashboard_users u ON u.id = a.user_id
                ORDER BY u.full_name
                """
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def add_cc_telegram_allowed_user(user_id: int) -> bool:
    """Add a user to the allowed list. Returns True on success."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO cc_telegram_allowed_users (user_id)
                VALUES (%(uid)s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                {"uid": user_id},
            )
        return True
    except Exception:
        return False


def remove_cc_telegram_allowed_user(user_id: int) -> bool:
    """Remove a user from the allowed list."""
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM cc_telegram_allowed_users WHERE user_id = %(uid)s", {"uid": user_id})
        return cur.rowcount > 0


def list_dashboard_admins_for_cc() -> list[dict]:
    """List dashboard users with role admin (for dropdown in CC Telegram settings)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, full_name, email
                FROM dashboard_users
                WHERE role = 'admin'
                ORDER BY full_name
                """
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Send Telegram notification for Call Center
# ---------------------------------------------------------------------------

def send_cc_telegram_notification(
    wa_user_name: str,
    message_preview: str,
) -> dict:
    """Send a Telegram notification to all CC groups about a new incoming message."""
    import urllib.request
    import urllib.parse
    import json as _json

    settings = fetch_cc_telegram_settings()
    bot_token = (settings.get("bot_token") or "").strip()
    if not bot_token:
        return {"skipped": "token_missing"}

    groups = list_cc_telegram_groups()
    if not groups:
        return {"skipped": "no_groups", "sent": 0}

    preview = (message_preview or "")[:200]
    text = (
        f"📞 *Pesan Masuk Call Center*\n\n"
        f"*Dari:* {_escape_md(wa_user_name)}\n"
        f"*Pesan:* {_escape_md(preview)}\n\n"
        f"Balas di Dashboard Call Center."
    )

    sent = 0
    for group in groups:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": group["chat_id"],
                "text": text,
                "parse_mode": "Markdown",
            }).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    sent += 1
        except Exception:
            traceback.print_exc()

    return {"sent": sent, "total_groups": len(groups)}


def _escape_md(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    for ch in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(ch, f"\\{ch}")
    return text
