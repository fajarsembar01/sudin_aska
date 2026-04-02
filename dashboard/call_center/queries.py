"""Database queries for the Call Center module."""

from __future__ import annotations

import os
import traceback
from typing import Optional, List, Dict, Any

from ..db_access import get_cursor

_CC_DRAFTS_SCHEMA_READY = False


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
# Message Drafts
# ---------------------------------------------------------------------------

def _ensure_cc_message_drafts_schema() -> None:
    """Ensure draft table exists for older deployments that haven't run schema updates yet."""
    global _CC_DRAFTS_SCHEMA_READY
    if _CC_DRAFTS_SCHEMA_READY:
        return

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cc_message_drafts (
                id SERIAL PRIMARY KEY,
                admin_user_id INTEGER NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Umum',
                message_text TEXT NOT NULL,
                pinned BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE cc_message_drafts
            ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cc_message_drafts_admin
            ON cc_message_drafts (admin_user_id, updated_at DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cc_message_drafts_admin_category
            ON cc_message_drafts (admin_user_id, category)
            """
        )
    _CC_DRAFTS_SCHEMA_READY = True


def list_cc_message_drafts(
    admin_user_id: int,
    category: Optional[str] = None,
) -> list[dict]:
    _ensure_cc_message_drafts_schema()
    params: dict[str, Any] = {"admin_user_id": admin_user_id}
    category_clause = ""
    if category:
        category_clause = "AND d.category = %(category)s"
        params["category"] = category

    with get_cursor() as cur:
        cur.execute(
            f"""
            WITH draft_usage AS (
                SELECT
                    target_id,
                    COUNT(*)::int AS usage_count
                FROM dashboard_admin_action_logs
                WHERE feature_key = 'call_center'
                  AND target_type = 'CALL_CENTER_DRAFT'
                  AND action IN ('USE', 'SEND')
                GROUP BY target_id
            )
            SELECT d.id, d.admin_user_id, d.title, d.category, d.message_text, d.pinned, d.created_at, d.updated_at
                 , COALESCE(du.usage_count, 0) AS usage_count
            FROM cc_message_drafts d
            LEFT JOIN draft_usage du ON du.target_id = d.id
            WHERE d.admin_user_id = %(admin_user_id)s {category_clause}
            ORDER BY d.pinned DESC, COALESCE(du.usage_count, 0) DESC, d.updated_at DESC, d.id DESC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def list_cc_message_draft_categories(admin_user_id: int) -> list[str]:
    _ensure_cc_message_drafts_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT d.category
            FROM cc_message_drafts d
            WHERE d.admin_user_id = %(admin_user_id)s
            GROUP BY d.category
            ORDER BY LOWER(d.category) ASC
            """,
            {"admin_user_id": admin_user_id},
        )
        return [str(r.get("category") or "") for r in cur.fetchall() if (r.get("category") or "").strip()]


def create_cc_message_draft(
    admin_user_id: int,
    title: str,
    category: str,
    message_text: str,
) -> dict:
    _ensure_cc_message_drafts_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_message_drafts (admin_user_id, title, category, message_text, pinned, updated_at)
            VALUES (%(admin_user_id)s, %(title)s, %(category)s, %(message_text)s, FALSE, NOW())
            RETURNING id, admin_user_id, title, category, message_text, pinned, created_at, updated_at
            """,
            {
                "admin_user_id": admin_user_id,
                "title": title,
                "category": category,
                "message_text": message_text,
            },
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def update_cc_message_draft(
    draft_id: int,
    admin_user_id: int,
    title: str,
    category: str,
    message_text: str,
) -> Optional[dict]:
    _ensure_cc_message_drafts_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE cc_message_drafts
            SET title = %(title)s,
                category = %(category)s,
                message_text = %(message_text)s,
                updated_at = NOW()
            WHERE id = %(draft_id)s AND admin_user_id = %(admin_user_id)s
            RETURNING id, admin_user_id, title, category, message_text, pinned, created_at, updated_at
            """,
            {
                "draft_id": draft_id,
                "admin_user_id": admin_user_id,
                "title": title,
                "category": category,
                "message_text": message_text,
            },
        )
        row = cur.fetchone()
    return dict(row) if row else None


def toggle_cc_message_draft_pin(draft_id: int, admin_user_id: int) -> Optional[dict]:
    _ensure_cc_message_drafts_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE cc_message_drafts
            SET pinned = NOT pinned,
                updated_at = NOW()
            WHERE id = %(draft_id)s
            RETURNING id, admin_user_id, title, category, message_text, pinned, created_at, updated_at
            """,
            {"draft_id": draft_id},
        )
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def delete_cc_message_draft(draft_id: int, admin_user_id: int) -> bool:
    _ensure_cc_message_drafts_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM cc_message_drafts
            WHERE id = %(draft_id)s AND admin_user_id = %(admin_user_id)s
            """,
            {"draft_id": draft_id, "admin_user_id": admin_user_id},
        )
        return cur.rowcount > 0


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
