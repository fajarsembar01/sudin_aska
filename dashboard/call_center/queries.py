"""Database queries for the Call Center module."""

from __future__ import annotations

import os
import re
import traceback
from typing import Optional, List, Dict, Any

from ..db_access import get_cursor

_CC_DRAFTS_SCHEMA_READY = False
_CC_MESSAGES_MEDIA_SCHEMA_READY = False
_CC_WA_ROUTING_SCHEMA_READY = False
_CC_WA_ROUTE_MODES = {"manual", "ai"}
_CC_BRIDGE_ACCOUNTS_SCHEMA_READY = False
_CC_BRIDGE_DEFAULT_KEY = "main"
_CC_BRIDGE_KEY_RE = re.compile(r"[^a-z0-9_-]+")


def _ensure_cc_messages_media_schema() -> None:
    """Ensure media columns exist for WhatsApp attachments."""
    global _CC_MESSAGES_MEDIA_SCHEMA_READY
    if _CC_MESSAGES_MEDIA_SCHEMA_READY:
        return

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                ALTER TABLE cc_messages
                ADD COLUMN IF NOT EXISTS media_path TEXT,
                ADD COLUMN IF NOT EXISTS media_mime_type TEXT,
                ADD COLUMN IF NOT EXISTS media_filename TEXT,
                ADD COLUMN IF NOT EXISTS media_size INTEGER,
                ADD COLUMN IF NOT EXISTS original_message_text TEXT,
                ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS edited_by_admin_user_id INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL
                """
            )
    except Exception as exc:
        msg = str(exc).lower()
        # Legacy databases may have cc_messages owned by another role.
        # In that case, skip ALTER and continue with existing schema.
        if "must be owner of table cc_messages" not in msg and "permission denied for table cc_messages" not in msg:
            raise
    _CC_MESSAGES_MEDIA_SCHEMA_READY = True


def _normalize_wa_user_id(raw_user_id: Optional[str]) -> str:
    return "".join(ch for ch in str(raw_user_id or "") if ch.isdigit())


def _normalize_route_mode(raw_mode: Optional[str]) -> str:
    mode = str(raw_mode or "manual").strip().lower()
    if mode not in _CC_WA_ROUTE_MODES:
        return "manual"
    return mode


def normalize_cc_route_mode(raw_mode: Optional[str]) -> str:
    """Public normalizer for route mode values used by routes/UI."""
    return _normalize_route_mode(raw_mode)


def _normalize_cc_bridge_filter(raw_bridge_key: Optional[str]) -> Optional[str]:
    raw = str(raw_bridge_key or "").strip().lower()
    if raw in {"", "all", "*"}:
        return None
    return normalize_cc_bridge_key(raw)


def _ensure_cc_wa_routing_schema() -> None:
    global _CC_WA_ROUTING_SCHEMA_READY
    if _CC_WA_ROUTING_SCHEMA_READY:
        return

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cc_wa_routing (
                id SERIAL PRIMARY KEY,
                bridge_key TEXT NOT NULL DEFAULT 'main',
                wa_user_id TEXT NOT NULL,
                display_name TEXT,
                route_mode TEXT NOT NULL DEFAULT 'manual' CHECK (route_mode IN ('manual','ai')),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by INTEGER
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE cc_wa_routing
            ADD COLUMN IF NOT EXISTS bridge_key TEXT NOT NULL DEFAULT 'main',
            ADD COLUMN IF NOT EXISTS route_mode TEXT NOT NULL DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS updated_by INTEGER,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """
        )
        cur.execute(
            """
            UPDATE cc_wa_routing
            SET bridge_key = 'main'
            WHERE bridge_key IS NULL OR bridge_key = ''
            """
        )
        cur.execute(
            """
            DO $$
            DECLARE
                legacy_unique_name TEXT;
                wa_attnum SMALLINT;
            BEGIN
                SELECT a.attnum
                INTO wa_attnum
                FROM pg_attribute a
                WHERE a.attrelid = 'cc_wa_routing'::regclass
                  AND a.attname = 'wa_user_id'
                  AND NOT a.attisdropped
                LIMIT 1;

                IF wa_attnum IS NOT NULL THEN
                    SELECT c.conname
                    INTO legacy_unique_name
                    FROM pg_constraint c
                    WHERE c.conrelid = 'cc_wa_routing'::regclass
                      AND c.contype = 'u'
                      AND array_length(c.conkey, 1) = 1
                      AND c.conkey[1] = wa_attnum
                    LIMIT 1;
                END IF;

                IF legacy_unique_name IS NOT NULL THEN
                    EXECUTE format(
                        'ALTER TABLE cc_wa_routing DROP CONSTRAINT %I',
                        legacy_unique_name
                    );
                END IF;
            END $$;
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'cc_wa_routing_route_mode_check'
                ) THEN
                    ALTER TABLE cc_wa_routing
                    ADD CONSTRAINT cc_wa_routing_route_mode_check
                    CHECK (route_mode IN ('manual','ai'));
                END IF;
            END $$;
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_wa_routing_bridge_user_unique
            ON cc_wa_routing (bridge_key, wa_user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cc_wa_routing_mode_active
            ON cc_wa_routing (bridge_key, route_mode, is_active)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cc_wa_routing_updated_at
            ON cc_wa_routing (updated_at DESC)
            """
        )
    _CC_WA_ROUTING_SCHEMA_READY = True


def ensure_cc_wa_routing_contact(
    wa_user_id: str,
    display_name: Optional[str] = None,
    route_mode: Optional[str] = None,
    bridge_key: Optional[str] = None,
) -> Optional[dict]:
    _ensure_cc_wa_routing_schema()
    key = normalize_cc_bridge_key(bridge_key)
    clean_wa = _normalize_wa_user_id(wa_user_id)
    if not clean_wa:
        return None

    clean_name = str(display_name or "").strip()[:120] or None
    mode = _normalize_route_mode(route_mode or "manual")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_wa_routing (
                bridge_key,
                wa_user_id,
                display_name,
                route_mode,
                is_active,
                updated_at
            )
            VALUES (
                %(bridge_key)s,
                %(wa)s,
                %(name)s,
                %(mode)s,
                TRUE,
                NOW()
            )
            ON CONFLICT (bridge_key, wa_user_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, cc_wa_routing.display_name),
                updated_at = NOW()
            RETURNING id, bridge_key, wa_user_id, display_name, route_mode, is_active, notes, created_at, updated_at, updated_by
            """,
            {"bridge_key": key, "wa": clean_wa, "name": clean_name, "mode": mode},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_cc_wa_routing(wa_user_id: str, *, bridge_key: Optional[str] = None) -> Optional[dict]:
    _ensure_cc_wa_routing_schema()
    key = normalize_cc_bridge_key(bridge_key)
    clean_wa = _normalize_wa_user_id(wa_user_id)
    if not clean_wa:
        return None
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.bridge_key, r.wa_user_id, r.display_name, r.route_mode, r.is_active, r.notes,
                   r.created_at, r.updated_at, r.updated_by
            FROM cc_wa_routing r
            WHERE r.bridge_key = %(bridge_key)s
              AND r.wa_user_id = %(wa)s
            LIMIT 1
            """,
            {"bridge_key": key, "wa": clean_wa},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_cc_wa_routing(
    search: Optional[str] = None,
    limit: int = 300,
    *,
    bridge_key: Optional[str] = None,
) -> list[dict]:
    _ensure_cc_wa_routing_schema()
    key = _normalize_cc_bridge_filter(bridge_key)
    clean_limit = max(1, min(int(limit or 300), 1000))
    params: dict[str, Any] = {"limit": clean_limit}
    where_parts: list[str] = []
    if key:
        where_parts.append("r.bridge_key = %(bridge_key)s")
        params["bridge_key"] = key
    clean_search = str(search or "").strip()
    if clean_search:
        where_parts.append("(r.wa_user_id ILIKE %(search)s OR r.display_name ILIKE %(search)s)")
        params["search"] = f"%{clean_search}%"
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT r.id, r.bridge_key, r.wa_user_id, r.display_name, r.route_mode, r.is_active, r.notes,
                   r.created_at, r.updated_at, r.updated_by,
                   c.id AS conversation_id,
                   c.status AS conversation_status,
                   c.last_message_at,
                   c.unread_count
            FROM cc_wa_routing r
            LEFT JOIN LATERAL (
                SELECT c1.id, c1.status, c1.last_message_at, c1.unread_count
                FROM cc_conversations c1
                WHERE (
                    (r.bridge_key = 'main' AND c1.wa_user_id = r.wa_user_id)
                    OR c1.wa_user_id = (r.bridge_key || '::' || r.wa_user_id)
                )
                ORDER BY c1.last_message_at DESC NULLS LAST, c1.id DESC
                LIMIT 1
            ) c ON TRUE
            {where}
            ORDER BY r.is_active DESC, r.updated_at DESC, r.id DESC
            LIMIT %(limit)s
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def summarize_cc_wa_routing(*, bridge_key: Optional[str] = None) -> dict:
    _ensure_cc_wa_routing_schema()
    key = _normalize_cc_bridge_filter(bridge_key)
    summary = {
        "total": 0,
        "active": 0,
        "inactive": 0,
        "manual": 0,
        "ai": 0,
    }
    with get_cursor() as cur:
        if key:
            cur.execute(
                """
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE is_active)::int AS active,
                    COUNT(*) FILTER (WHERE NOT is_active)::int AS inactive,
                    COUNT(*) FILTER (WHERE route_mode = 'manual')::int AS manual,
                    COUNT(*) FILTER (WHERE route_mode = 'ai')::int AS ai
                FROM cc_wa_routing
                WHERE bridge_key = %(bridge_key)s
                """,
                {"bridge_key": key},
            )
        else:
            cur.execute(
                """
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE is_active)::int AS active,
                    COUNT(*) FILTER (WHERE NOT is_active)::int AS inactive,
                    COUNT(*) FILTER (WHERE route_mode = 'manual')::int AS manual,
                    COUNT(*) FILTER (WHERE route_mode = 'ai')::int AS ai
                FROM cc_wa_routing
                """
            )
        row = cur.fetchone() or {}
    summary.update(
        {
            "total": int(row.get("total") or 0),
            "active": int(row.get("active") or 0),
            "inactive": int(row.get("inactive") or 0),
            "manual": int(row.get("manual") or 0),
            "ai": int(row.get("ai") or 0),
        }
    )
    return summary


def save_cc_wa_routing(
    wa_user_id: str,
    *,
    bridge_key: Optional[str] = None,
    display_name: Optional[str] = None,
    route_mode: str = "manual",
    is_active: bool = True,
    notes: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> dict:
    _ensure_cc_wa_routing_schema()
    key = normalize_cc_bridge_key(bridge_key)
    clean_wa = _normalize_wa_user_id(wa_user_id)
    if not clean_wa:
        raise ValueError("Nomor WA tidak valid.")

    clean_name = str(display_name or "").strip()[:120] or None
    clean_notes = str(notes or "").strip()[:1000] or None
    mode = _normalize_route_mode(route_mode)

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_wa_routing (
                bridge_key,
                wa_user_id,
                display_name,
                route_mode,
                is_active,
                notes,
                updated_by,
                updated_at
            )
            VALUES (
                %(bridge_key)s,
                %(wa)s,
                %(name)s,
                %(mode)s,
                %(active)s,
                %(notes)s,
                %(updated_by)s,
                NOW()
            )
            ON CONFLICT (bridge_key, wa_user_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, cc_wa_routing.display_name),
                route_mode = EXCLUDED.route_mode,
                is_active = EXCLUDED.is_active,
                notes = EXCLUDED.notes,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING id, bridge_key, wa_user_id, display_name, route_mode, is_active, notes, created_at, updated_at, updated_by
            """,
            {
                "bridge_key": key,
                "wa": clean_wa,
                "name": clean_name,
                "mode": mode,
                "active": bool(is_active),
                "notes": clean_notes,
                "updated_by": updated_by,
            },
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def delete_cc_wa_routing(wa_user_id: str, *, bridge_key: Optional[str] = None) -> bool:
    _ensure_cc_wa_routing_schema()
    key = normalize_cc_bridge_key(bridge_key)
    clean_wa = _normalize_wa_user_id(wa_user_id)
    if not clean_wa:
        return False
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM cc_wa_routing WHERE bridge_key = %(bridge_key)s AND wa_user_id = %(wa)s",
            {"bridge_key": key, "wa": clean_wa},
        )
        return cur.rowcount > 0


def normalize_cc_bridge_key(raw_key: Optional[str]) -> str:
    clean = str(raw_key or "").strip().lower()
    clean = _CC_BRIDGE_KEY_RE.sub("-", clean).strip("-")
    return clean or _CC_BRIDGE_DEFAULT_KEY


def compose_cc_conversation_user_key(raw_wa_user_id: str, bridge_key: Optional[str]) -> str:
    clean_wa = _normalize_wa_user_id(raw_wa_user_id)
    key = normalize_cc_bridge_key(bridge_key)
    if not clean_wa:
        return ""
    if key == _CC_BRIDGE_DEFAULT_KEY:
        return clean_wa
    return f"{key}::{clean_wa}"


def split_cc_conversation_user_key(wa_user_id: Optional[str]) -> dict:
    raw = str(wa_user_id or "").strip()
    if not raw:
        return {
            "bridge_key": _CC_BRIDGE_DEFAULT_KEY,
            "raw_wa_user_id": "",
            "conversation_user_key": "",
        }
    if "::" in raw:
        maybe_key, maybe_wa = raw.split("::", 1)
        parsed_key = normalize_cc_bridge_key(maybe_key)
        clean_wa = _normalize_wa_user_id(maybe_wa)
        if clean_wa:
            return {
                "bridge_key": parsed_key,
                "raw_wa_user_id": clean_wa,
                "conversation_user_key": raw,
            }
    return {
        "bridge_key": _CC_BRIDGE_DEFAULT_KEY,
        "raw_wa_user_id": _normalize_wa_user_id(raw),
        "conversation_user_key": raw,
    }


def enrich_cc_conversation_row(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return row
    parsed = split_cc_conversation_user_key(row.get("wa_user_id"))
    row["conversation_user_key"] = parsed["conversation_user_key"]
    row["bridge_key"] = parsed["bridge_key"]
    row["wa_user_id_raw"] = parsed["raw_wa_user_id"] or str(row.get("wa_user_id") or "")
    return row


def _bridge_defaults_for_key(bridge_key: str) -> dict:
    key = normalize_cc_bridge_key(bridge_key)
    if key == _CC_BRIDGE_DEFAULT_KEY:
        return {
            "display_name": "WA Main",
            "client_id": "cc-main",
            "http_port": 3100,
            "session_path": ".wa_cc_session",
            "status_path": "runtime/whatsapp_cc_status.json",
            "pid_path": "runtime/whatsapp_cc.pid",
            "log_path": "runtime/whatsapp_cc.log",
            "internal_url": os.getenv("ASKA_CC_WHATSAPP_INTERNAL_URL") or "http://127.0.0.1:5002/api/callcenter/inbound",
            "is_active": True,
            "default_route_mode": "manual",
        }
    return {
        "display_name": f"WA {key.upper()}",
        "client_id": f"cc-{key}",
        "http_port": 3200,
        "session_path": f".wa_cc_session_{key}",
        "status_path": f"runtime/whatsapp_cc_status_{key}.json",
        "pid_path": f"runtime/whatsapp_cc_{key}.pid",
        "log_path": f"runtime/whatsapp_cc_{key}.log",
        "internal_url": os.getenv("ASKA_CC_WHATSAPP_INTERNAL_URL") or "http://127.0.0.1:5002/api/callcenter/inbound",
        "is_active": True,
        "default_route_mode": "manual",
    }


def _ensure_cc_wa_bridge_accounts_schema() -> None:
    global _CC_BRIDGE_ACCOUNTS_SCHEMA_READY
    if _CC_BRIDGE_ACCOUNTS_SCHEMA_READY:
        return

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cc_wa_bridge_accounts (
                id SERIAL PRIMARY KEY,
                bridge_key TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                wa_number_hint TEXT,
                default_route_mode TEXT NOT NULL DEFAULT 'manual' CHECK (default_route_mode IN ('manual','ai')),
                client_id TEXT NOT NULL,
                http_port INTEGER NOT NULL UNIQUE,
                session_path TEXT NOT NULL,
                status_path TEXT NOT NULL,
                pid_path TEXT NOT NULL,
                log_path TEXT NOT NULL,
                internal_url TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by INTEGER
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE cc_wa_bridge_accounts
            ADD COLUMN IF NOT EXISTS wa_number_hint TEXT,
            ADD COLUMN IF NOT EXISTS default_route_mode TEXT NOT NULL DEFAULT 'manual'
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'cc_wa_bridge_accounts_default_route_mode_check'
                ) THEN
                    ALTER TABLE cc_wa_bridge_accounts
                    ADD CONSTRAINT cc_wa_bridge_accounts_default_route_mode_check
                    CHECK (default_route_mode IN ('manual','ai'));
                END IF;
            END $$;
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cc_wa_bridge_accounts_active
            ON cc_wa_bridge_accounts (is_active, bridge_key)
            """
        )
    _CC_BRIDGE_ACCOUNTS_SCHEMA_READY = True


def ensure_default_cc_wa_bridge_account(updated_by: Optional[int] = None) -> dict:
    _ensure_cc_wa_bridge_accounts_schema()
    existing = get_cc_wa_bridge_account(_CC_BRIDGE_DEFAULT_KEY)
    if existing:
        return existing
    defaults = _bridge_defaults_for_key(_CC_BRIDGE_DEFAULT_KEY)
    return save_cc_wa_bridge_account(
        bridge_key=_CC_BRIDGE_DEFAULT_KEY,
        display_name=defaults["display_name"],
        wa_number_hint=None,
        default_route_mode=defaults["default_route_mode"],
        client_id=defaults["client_id"],
        http_port=defaults["http_port"],
        session_path=defaults["session_path"],
        status_path=defaults["status_path"],
        pid_path=defaults["pid_path"],
        log_path=defaults["log_path"],
        internal_url=defaults["internal_url"],
        is_active=defaults["is_active"],
        updated_by=updated_by,
    )


def list_cc_wa_bridge_accounts(*, include_inactive: bool = True) -> list[dict]:
    _ensure_cc_wa_bridge_accounts_schema()
    where = "" if include_inactive else "WHERE is_active = TRUE"
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT id, bridge_key, display_name, wa_number_hint, default_route_mode, client_id, http_port,
                   session_path, status_path, pid_path, log_path,
                   internal_url, is_active, created_at, updated_at, updated_by
            FROM cc_wa_bridge_accounts
            {where}
            ORDER BY CASE WHEN bridge_key = 'main' THEN 0 ELSE 1 END, bridge_key ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]


def get_cc_wa_bridge_account(bridge_key: Optional[str]) -> Optional[dict]:
    _ensure_cc_wa_bridge_accounts_schema()
    key = normalize_cc_bridge_key(bridge_key)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, bridge_key, display_name, wa_number_hint, default_route_mode, client_id, http_port,
                   session_path, status_path, pid_path, log_path,
                   internal_url, is_active, created_at, updated_at, updated_by
            FROM cc_wa_bridge_accounts
            WHERE bridge_key = %(bridge_key)s
            LIMIT 1
            """,
            {"bridge_key": key},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def find_cc_wa_bridge_account_by_port(http_port: int) -> Optional[dict]:
    _ensure_cc_wa_bridge_accounts_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, bridge_key, display_name, wa_number_hint, default_route_mode, client_id, http_port,
                   session_path, status_path, pid_path, log_path,
                   internal_url, is_active, created_at, updated_at, updated_by
            FROM cc_wa_bridge_accounts
            WHERE http_port = %(http_port)s
            LIMIT 1
            """,
            {"http_port": int(http_port)},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _find_next_available_bridge_port(start_port: int, *, bridge_key: str) -> int:
    """Find next free bridge HTTP port starting from start_port."""
    _ensure_cc_wa_bridge_accounts_schema()
    start = max(1, int(start_port or 1))
    key = normalize_cc_bridge_key(bridge_key)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT bridge_key, http_port
            FROM cc_wa_bridge_accounts
            WHERE http_port >= %(start)s
            ORDER BY http_port ASC
            """,
            {"start": start},
        )
        rows = [dict(r) for r in cur.fetchall()]

    candidate = start
    for row in rows:
        row_key = normalize_cc_bridge_key(row.get("bridge_key"))
        if row_key == key:
            continue
        used_port = int(row.get("http_port") or 0)
        if used_port < candidate:
            continue
        if used_port == candidate:
            candidate += 1
            if candidate > 65535:
                raise ValueError("Tidak ada HTTP port yang tersedia untuk akun bridge.")
            continue
        break

    if candidate > 65535:
        raise ValueError("Tidak ada HTTP port yang tersedia untuk akun bridge.")
    return candidate


def save_cc_wa_bridge_account(
    *,
    bridge_key: str,
    display_name: Optional[str],
    wa_number_hint: Optional[str],
    default_route_mode: Optional[str],
    client_id: Optional[str],
    http_port: Optional[int],
    session_path: Optional[str],
    status_path: Optional[str],
    pid_path: Optional[str],
    log_path: Optional[str],
    internal_url: Optional[str],
    is_active: bool,
    updated_by: Optional[int] = None,
) -> dict:
    _ensure_cc_wa_bridge_accounts_schema()
    key = normalize_cc_bridge_key(bridge_key)
    defaults = _bridge_defaults_for_key(key)
    existing = get_cc_wa_bridge_account(key)

    clean_display_name = str(display_name or "").strip() or defaults["display_name"]
    clean_wa_hint = _normalize_wa_user_id(wa_number_hint) or None
    raw_default_route_mode = str(default_route_mode or "").strip()
    if raw_default_route_mode:
        clean_default_route_mode = _normalize_route_mode(raw_default_route_mode)
    elif existing and existing.get("default_route_mode"):
        clean_default_route_mode = _normalize_route_mode(existing.get("default_route_mode"))
    else:
        clean_default_route_mode = _normalize_route_mode(defaults["default_route_mode"])
    clean_client_id = str(client_id or "").strip() or defaults["client_id"]
    try:
        requested_http_port = int(http_port or 0)
    except Exception:
        requested_http_port = 0
    if requested_http_port > 0:
        clean_http_port = requested_http_port
    elif existing and existing.get("http_port"):
        clean_http_port = int(existing.get("http_port") or 0)
    else:
        clean_http_port = _find_next_available_bridge_port(
            int(defaults["http_port"]),
            bridge_key=key,
        )
    clean_session_path = str(session_path or "").strip() or defaults["session_path"]
    clean_status_path = str(status_path or "").strip() or defaults["status_path"]
    clean_pid_path = str(pid_path or "").strip() or defaults["pid_path"]
    clean_log_path = str(log_path or "").strip() or defaults["log_path"]
    clean_internal_url = str(internal_url or "").strip() or defaults["internal_url"]

    if clean_http_port < 1 or clean_http_port > 65535:
        raise ValueError("HTTP port bridge tidak valid.")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_wa_bridge_accounts (
                bridge_key, display_name, wa_number_hint, default_route_mode, client_id, http_port,
                session_path, status_path, pid_path, log_path,
                internal_url, is_active, updated_by, updated_at
            )
            VALUES (
                %(bridge_key)s, %(display_name)s, %(wa_number_hint)s, %(default_route_mode)s, %(client_id)s, %(http_port)s,
                %(session_path)s, %(status_path)s, %(pid_path)s, %(log_path)s,
                %(internal_url)s, %(is_active)s, %(updated_by)s, NOW()
            )
            ON CONFLICT (bridge_key) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                wa_number_hint = EXCLUDED.wa_number_hint,
                default_route_mode = EXCLUDED.default_route_mode,
                client_id = EXCLUDED.client_id,
                http_port = EXCLUDED.http_port,
                session_path = EXCLUDED.session_path,
                status_path = EXCLUDED.status_path,
                pid_path = EXCLUDED.pid_path,
                log_path = EXCLUDED.log_path,
                internal_url = EXCLUDED.internal_url,
                is_active = EXCLUDED.is_active,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING id, bridge_key, display_name, wa_number_hint, default_route_mode, client_id, http_port,
                      session_path, status_path, pid_path, log_path,
                      internal_url, is_active, created_at, updated_at, updated_by
            """,
            {
                "bridge_key": key,
                "display_name": clean_display_name,
                "wa_number_hint": clean_wa_hint,
                "default_route_mode": clean_default_route_mode,
                "client_id": clean_client_id,
                "http_port": clean_http_port,
                "session_path": clean_session_path,
                "status_path": clean_status_path,
                "pid_path": clean_pid_path,
                "log_path": clean_log_path,
                "internal_url": clean_internal_url,
                "is_active": bool(is_active),
                "updated_by": updated_by,
            },
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def delete_cc_wa_bridge_account(bridge_key: str) -> bool:
    _ensure_cc_wa_bridge_accounts_schema()
    key = normalize_cc_bridge_key(bridge_key)
    if key == _CC_BRIDGE_DEFAULT_KEY:
        return False
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM cc_wa_bridge_accounts WHERE bridge_key = %(bridge_key)s",
            {"bridge_key": key},
        )
        return cur.rowcount > 0


def get_default_cc_wa_bridge_account() -> dict:
    ensure_default_cc_wa_bridge_account()
    account = get_cc_wa_bridge_account(_CC_BRIDGE_DEFAULT_KEY)
    if account:
        return account
    accounts = list_cc_wa_bridge_accounts(include_inactive=False)
    if accounts:
        return accounts[0]
    return ensure_default_cc_wa_bridge_account()


def list_cc_bridge_keys_in_use() -> list[str]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT wa_user_id
            FROM cc_conversations
            WHERE wa_user_id IS NOT NULL
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    keys = set()
    for row in rows:
        parsed = split_cc_conversation_user_key(row.get("wa_user_id"))
        if parsed["bridge_key"]:
            keys.add(parsed["bridge_key"])
    return sorted(keys)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def upsert_cc_conversation(
    wa_user_id: str,
    display_name: Optional[str] = None,
    last_message_at: Optional[str] = None,
) -> dict:
    """Create or update a conversation for the given WA user.

    Returns the conversation row as a dict.
    """
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_conversations (wa_user_id, display_name, last_message_at, updated_at)
            VALUES (%(wa)s, %(name)s, COALESCE(%(last_message_at)s::timestamptz, NOW()), NOW())
            ON CONFLICT (wa_user_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, cc_conversations.display_name),
                last_message_at = GREATEST(
                    COALESCE(cc_conversations.last_message_at, EXCLUDED.last_message_at),
                    EXCLUDED.last_message_at
                ),
                updated_at = NOW()
            RETURNING id, wa_user_id, display_name, status, last_message_at,
                      unread_count, created_at, updated_at
            """,
            {"wa": wa_user_id, "name": display_name, "last_message_at": last_message_at},
        )
        row = cur.fetchone()
    return enrich_cc_conversation_row(dict(row)) if row else {}


def fetch_cc_conversations(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    bridge_key: Optional[str] = None,
    limit: Optional[int] = 100,
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
            """
            (
                c.display_name ILIKE %(search)s
                OR c.wa_user_id ILIKE %(search)s
                OR EXISTS (
                    SELECT 1
                    FROM cc_messages m_search
                    WHERE m_search.conversation_id = c.id
                      AND (
                          m_search.message_text ILIKE %(search)s
                          OR COALESCE(m_search.original_message_text, '') ILIKE %(search)s
                      )
                )
            )
            """
        )
        params["search"] = f"%{search}%"

    selected_bridge_key = _normalize_cc_bridge_filter(bridge_key)
    if selected_bridge_key:
        if selected_bridge_key == _CC_BRIDGE_DEFAULT_KEY:
            conditions.append("POSITION('::' IN COALESCE(c.wa_user_id, '')) = 0")
        else:
            conditions.append("c.wa_user_id LIKE %(bridge_prefix)s")
            params["bridge_prefix"] = f"{selected_bridge_key}::%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS cnt FROM cc_conversations c {where}", params
        )
        total = (cur.fetchone() or {}).get("cnt", 0)

        paging_clause = ""
        paging_params = dict(params)

        if limit is not None:
            paging_clause = "LIMIT %(limit)s OFFSET %(offset)s"
            paging_params["limit"] = max(1, int(limit))
            paging_params["offset"] = max(0, int(offset))
        elif offset:
            paging_clause = "OFFSET %(offset)s"
            paging_params["offset"] = max(0, int(offset))

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
            {paging_clause}
            """,
            paging_params,
        )
        rows = [enrich_cc_conversation_row(dict(r)) for r in cur.fetchall()]

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
    return enrich_cc_conversation_row(dict(row)) if row else None


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
# Statistics
# ---------------------------------------------------------------------------

def fetch_cc_statistics(
    *,
    period_mode: str = "daily",
    selected_date: Optional[str] = None,
    selected_month: Optional[str] = None,
    selected_year: Optional[int] = None,
    bridge_key: Optional[str] = None,
) -> dict:
    """Return call center statistics (messages, conversation activity, jenjang, issues)."""
    mode = (period_mode or "daily").strip().lower()
    if mode not in {"daily", "monthly", "yearly", "all"}:
        mode = "daily"

    msg_conditions = ["m.direction = 'inbound'"]
    conv_conditions: list[str] = []
    msg_params: dict[str, Any] = {}
    conv_params: dict[str, Any] = {}

    selected_bridge_key = _normalize_cc_bridge_filter(bridge_key)
    if selected_bridge_key:
        if selected_bridge_key == _CC_BRIDGE_DEFAULT_KEY:
            msg_conditions.append("POSITION('::' IN COALESCE(c.wa_user_id, '')) = 0")
            conv_conditions.append("POSITION('::' IN COALESCE(c.wa_user_id, '')) = 0")
        else:
            msg_conditions.append("c.wa_user_id LIKE %(bridge_prefix)s")
            conv_conditions.append("c.wa_user_id LIKE %(bridge_prefix)s")
            msg_params["bridge_prefix"] = f"{selected_bridge_key}::%"
            conv_params["bridge_prefix"] = f"{selected_bridge_key}::%"

    if mode == "daily" and selected_date:
        msg_conditions.append("timezone('Asia/Jakarta', m.created_at)::date = %(selected_date)s::date")
        conv_conditions.append("timezone('Asia/Jakarta', c.created_at)::date = %(selected_date)s::date")
        msg_params["selected_date"] = selected_date
        conv_params["selected_date"] = selected_date
    elif mode == "monthly" and selected_month:
        msg_conditions.append("to_char(timezone('Asia/Jakarta', m.created_at), 'YYYY-MM') = %(selected_month)s")
        conv_conditions.append("to_char(timezone('Asia/Jakarta', c.created_at), 'YYYY-MM') = %(selected_month)s")
        msg_params["selected_month"] = selected_month
        conv_params["selected_month"] = selected_month
    elif mode == "yearly" and selected_year:
        msg_conditions.append("EXTRACT(YEAR FROM timezone('Asia/Jakarta', m.created_at)) = %(selected_year)s")
        conv_conditions.append("EXTRACT(YEAR FROM timezone('Asia/Jakarta', c.created_at)) = %(selected_year)s")
        msg_params["selected_year"] = int(selected_year)
        conv_params["selected_year"] = int(selected_year)

    where_msg = ("WHERE " + " AND ".join(msg_conditions)) if msg_conditions else ""
    where_conv = ("WHERE " + " AND ".join(conv_conditions)) if conv_conditions else ""

    jenjang_case_sql = """
        CASE
            WHEN txt ~* '(^|[^a-z0-9])(smk|sekolah menengah kejuruan)([^a-z0-9]|$)' THEN 'SMK'
            WHEN txt ~* '(^|[^a-z0-9])(sma|sekolah menengah atas|madrasah aliyah)([^a-z0-9]|$)' THEN 'SMA'
            WHEN txt ~* '(^|[^a-z0-9])(smp|mts|sekolah menengah pertama|madrasah tsanawiyah)([^a-z0-9]|$)' THEN 'SMP'
            WHEN txt ~* '(^|[^a-z0-9])(tk|paud|taman kanak|kelompok bermain|sekolah dasar|sd)([^a-z0-9]|$)' THEN 'TK/SD'
            ELSE 'Tidak diketahui'
        END
    """
    issue_case_sql = """
        CASE
            WHEN txt ~* '(nik|ktp|kk|kartu keluarga|akta lahir|akta kematian|domisili|pindah|penduduk|disdukcapil|capil)' THEN 'Kependudukan'
            WHEN txt ~* '(error|gagal|tidak bisa|gabisa|nggak bisa|gangguan|bug|server|login|aplikasi|website|situs|otp|verifikasi|jaringan|timeout)' THEN 'Teknis'
            WHEN txt ~* '(regulasi|aturan|peraturan|kebijakan|syarat|ketentuan|dasar hukum|payung hukum|pergub|perda|undang-undang|uu|juknis|sop)' THEN 'Regulasi'
            ELSE 'Lainnya'
        END
    """

    summary = {
        "total_messages": 0,
        "unique_numbers": 0,
        "active_contact_days": 0,
        "new_conversations": 0,
    }
    message_timeline: list[dict] = []
    conversation_timeline: list[dict] = []
    jenjang_stats: list[dict] = []
    issue_stats: list[dict] = []

    with get_cursor() as cur:
        cur.execute(
            f"""
            WITH msg_base AS (
                SELECT
                    c.wa_user_id,
                    timezone('Asia/Jakarta', m.created_at)::date AS local_date
                FROM cc_messages m
                JOIN cc_conversations c ON c.id = m.conversation_id
                {where_msg}
            )
            SELECT
                COUNT(*)::int AS total_messages,
                COUNT(DISTINCT wa_user_id)::int AS unique_numbers,
                COUNT(DISTINCT (local_date, wa_user_id))::int AS active_contact_days
            FROM msg_base
            """,
            msg_params,
        )
        row = dict(cur.fetchone() or {})
        summary["total_messages"] = int(row.get("total_messages") or 0)
        summary["unique_numbers"] = int(row.get("unique_numbers") or 0)
        summary["active_contact_days"] = int(row.get("active_contact_days") or 0)

        cur.execute(
            f"""
            SELECT COUNT(*)::int AS total
            FROM cc_conversations c
            {where_conv}
            """,
            conv_params,
        )
        row = dict(cur.fetchone() or {})
        summary["new_conversations"] = int(row.get("total") or 0)

        cur.execute(
            f"""
            WITH msg_base AS (
                SELECT
                    c.wa_user_id,
                    timezone('Asia/Jakarta', m.created_at)::date AS local_date
                FROM cc_messages m
                JOIN cc_conversations c ON c.id = m.conversation_id
                {where_msg}
            )
            SELECT
                local_date,
                COUNT(*)::int AS total_messages,
                COUNT(DISTINCT wa_user_id)::int AS unique_numbers,
                COUNT(DISTINCT (local_date, wa_user_id))::int AS active_contact_days
            FROM msg_base
            GROUP BY local_date
            ORDER BY local_date ASC
            """,
            msg_params,
        )
        message_timeline = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT
                timezone('Asia/Jakarta', c.created_at)::date AS local_date,
                COUNT(*)::int AS total_new_conversations
            FROM cc_conversations c
            {where_conv}
            GROUP BY local_date
            ORDER BY local_date ASC
            """,
            conv_params,
        )
        conversation_timeline = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"""
            WITH msg_base AS (
                SELECT
                    c.wa_user_id,
                    timezone('Asia/Jakarta', m.created_at)::date AS local_date,
                    LOWER(COALESCE(m.message_text, '')) AS txt
                FROM cc_messages m
                JOIN cc_conversations c ON c.id = m.conversation_id
                {where_msg}
            ),
            classified AS (
                SELECT
                    wa_user_id,
                    local_date,
                    {jenjang_case_sql} AS jenjang
                FROM msg_base
            ),
            dominant_per_number AS (
                SELECT DISTINCT ON (wa_user_id)
                    wa_user_id,
                    jenjang
                FROM (
                    SELECT
                        wa_user_id,
                        jenjang,
                        COUNT(*)::int AS hit_count,
                        COUNT(DISTINCT local_date)::int AS day_count,
                        CASE
                            WHEN jenjang = 'TK/SD' THEN 1
                            WHEN jenjang = 'SMP' THEN 2
                            WHEN jenjang = 'SMA' THEN 3
                            WHEN jenjang = 'SMK' THEN 4
                            ELSE 9
                        END AS priority_rank
                    FROM classified
                    GROUP BY wa_user_id, jenjang
                ) score
                ORDER BY wa_user_id, hit_count DESC, day_count DESC, priority_rank ASC, jenjang ASC
            ),
            assigned_messages AS (
                SELECT
                    d.jenjang,
                    COUNT(*)::int AS total_messages
                FROM classified c
                JOIN dominant_per_number d ON d.wa_user_id = c.wa_user_id
                GROUP BY d.jenjang
            ),
            assigned_unique_numbers AS (
                SELECT
                    jenjang,
                    COUNT(*)::int AS unique_numbers
                FROM dominant_per_number
                GROUP BY jenjang
            ),
            assigned_contact_days AS (
                SELECT
                    d.jenjang,
                    COUNT(*)::int AS active_contact_days
                FROM (
                    SELECT DISTINCT wa_user_id, local_date
                    FROM classified
                ) ud
                JOIN dominant_per_number d ON d.wa_user_id = ud.wa_user_id
                GROUP BY d.jenjang
            )
            SELECT
                k.jenjang,
                COALESCE(m.total_messages, 0) AS total_messages,
                COALESCE(u.unique_numbers, 0) AS unique_numbers,
                COALESCE(a.active_contact_days, 0) AS active_contact_days
            FROM (
                VALUES ('TK/SD'), ('SMP'), ('SMA'), ('SMK'), ('Tidak diketahui')
            ) AS k(jenjang)
            LEFT JOIN assigned_messages m ON m.jenjang = k.jenjang
            LEFT JOIN assigned_unique_numbers u ON u.jenjang = k.jenjang
            LEFT JOIN assigned_contact_days a ON a.jenjang = k.jenjang
            ORDER BY
                CASE k.jenjang
                    WHEN 'TK/SD' THEN 1
                    WHEN 'SMP' THEN 2
                    WHEN 'SMA' THEN 3
                    WHEN 'SMK' THEN 4
                    ELSE 9
                END
            """,
            msg_params,
        )
        jenjang_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"""
            WITH msg_base AS (
                SELECT
                    c.wa_user_id,
                    timezone('Asia/Jakarta', m.created_at)::date AS local_date,
                    LOWER(COALESCE(m.message_text, '')) AS txt
                FROM cc_messages m
                JOIN cc_conversations c ON c.id = m.conversation_id
                {where_msg}
            ),
            classified AS (
                SELECT
                    wa_user_id,
                    local_date,
                    {issue_case_sql} AS issue_category
                FROM msg_base
            ),
            dominant_per_number AS (
                SELECT DISTINCT ON (wa_user_id)
                    wa_user_id,
                    issue_category
                FROM (
                    SELECT
                        wa_user_id,
                        issue_category,
                        COUNT(*)::int AS hit_count,
                        COUNT(DISTINCT local_date)::int AS day_count,
                        CASE
                            WHEN issue_category = 'Kependudukan' THEN 1
                            WHEN issue_category = 'Teknis' THEN 2
                            WHEN issue_category = 'Regulasi' THEN 3
                            ELSE 9
                        END AS priority_rank
                    FROM classified
                    GROUP BY wa_user_id, issue_category
                ) score
                ORDER BY wa_user_id, hit_count DESC, day_count DESC, priority_rank ASC, issue_category ASC
            ),
            assigned_messages AS (
                SELECT
                    d.issue_category,
                    COUNT(*)::int AS total_messages
                FROM classified c
                JOIN dominant_per_number d ON d.wa_user_id = c.wa_user_id
                GROUP BY d.issue_category
            ),
            assigned_unique_numbers AS (
                SELECT
                    issue_category,
                    COUNT(*)::int AS unique_numbers
                FROM dominant_per_number
                GROUP BY issue_category
            ),
            assigned_contact_days AS (
                SELECT
                    d.issue_category,
                    COUNT(*)::int AS active_contact_days
                FROM (
                    SELECT DISTINCT wa_user_id, local_date
                    FROM classified
                ) ud
                JOIN dominant_per_number d ON d.wa_user_id = ud.wa_user_id
                GROUP BY d.issue_category
            )
            SELECT
                k.issue_category,
                COALESCE(m.total_messages, 0) AS total_messages,
                COALESCE(u.unique_numbers, 0) AS unique_numbers,
                COALESCE(a.active_contact_days, 0) AS active_contact_days
            FROM (
                VALUES ('Kependudukan'), ('Teknis'), ('Regulasi'), ('Lainnya')
            ) AS k(issue_category)
            LEFT JOIN assigned_messages m ON m.issue_category = k.issue_category
            LEFT JOIN assigned_unique_numbers u ON u.issue_category = k.issue_category
            LEFT JOIN assigned_contact_days a ON a.issue_category = k.issue_category
            ORDER BY
                CASE k.issue_category
                    WHEN 'Kependudukan' THEN 1
                    WHEN 'Teknis' THEN 2
                    WHEN 'Regulasi' THEN 3
                    ELSE 9
                END
            """,
            msg_params,
        )
        issue_stats = [dict(r) for r in cur.fetchall()]

    return {
        "mode": mode,
        "summary": summary,
        "message_timeline": message_timeline,
        "conversation_timeline": conversation_timeline,
        "jenjang_stats": jenjang_stats,
        "issue_stats": issue_stats,
    }


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
    created_at: Optional[str] = None,
    increment_unread: bool = True,
    media_path: Optional[str] = None,
    media_mime_type: Optional[str] = None,
    media_filename: Optional[str] = None,
    media_size: Optional[int] = None,
) -> dict:
    """Insert a message and update conversation timestamps/unread."""
    _ensure_cc_messages_media_schema()
    with get_cursor(commit=True) as cur:
        if wa_message_id:
            cur.execute(
                """
                SELECT id, conversation_id, direction, message_text,
                       admin_user_id, admin_display_name, wa_message_id, created_at,
                       media_path, media_mime_type, media_filename, media_size,
                       original_message_text, edited_at, edited_by_admin_user_id
                FROM cc_messages
                WHERE wa_message_id = %(wa_msg)s
                LIMIT 1
                """,
                {"wa_msg": wa_message_id},
            )
            existing = cur.fetchone()
            if existing:
                duplicate = dict(existing)
                duplicate["duplicate"] = True
                return duplicate

        cur.execute(
            """
            INSERT INTO cc_messages
                (conversation_id, direction, message_text,
                 admin_user_id, admin_display_name, wa_message_id, created_at,
                 media_path, media_mime_type, media_filename, media_size)
            VALUES (
                %(conv)s, %(dir)s, %(text)s, %(admin)s, %(admin_name)s, %(wa_msg)s,
                COALESCE(%(created_at)s::timestamptz, NOW()),
                %(media_path)s, %(media_mime_type)s, %(media_filename)s, %(media_size)s
            )
            RETURNING id, conversation_id, direction, message_text,
                      admin_user_id, admin_display_name, wa_message_id, created_at,
                      media_path, media_mime_type, media_filename, media_size,
                      original_message_text, edited_at, edited_by_admin_user_id
            """,
            {
                "conv": conversation_id,
                "dir": direction,
                "text": message_text,
                "admin": admin_user_id,
                "admin_name": admin_display_name,
                "wa_msg": wa_message_id,
                "created_at": created_at,
                "media_path": media_path,
                "media_mime_type": media_mime_type,
                "media_filename": media_filename,
                "media_size": media_size,
            },
        )
        row = cur.fetchone()
        message_created_at = row["created_at"] if row else None

        # Update conversation
        if direction == "inbound":
            cur.execute(
                """
                UPDATE cc_conversations
                SET last_message_at = GREATEST(
                        COALESCE(last_message_at, %(created_at)s),
                        %(created_at)s
                    ),
                    unread_count = unread_count + %(unread_delta)s,
                    status = 'open',
                    updated_at = NOW()
                WHERE id = %(conv)s
                """,
                {
                    "conv": conversation_id,
                    "created_at": message_created_at,
                    "unread_delta": 1 if increment_unread else 0,
                },
            )
        else:
            cur.execute(
                """
                UPDATE cc_conversations
                SET last_message_at = GREATEST(
                        COALESCE(last_message_at, %(created_at)s),
                        %(created_at)s
                    ),
                    updated_at = NOW()
                WHERE id = %(conv)s
                """,
                {"conv": conversation_id, "created_at": message_created_at},
            )

    return dict(row) if row else {}


def fetch_cc_messages(
    conversation_id: int,
    limit: int = 200,
    after_id: Optional[int] = None,
) -> list[dict]:
    """Fetch messages for a conversation, optionally only those after a given ID."""
    _ensure_cc_messages_media_schema()
    params: dict = {"conv": conversation_id, "limit": limit}
    after_clause = ""
    if after_id:
        after_clause = "AND m.id > %(after_id)s"
        params["after_id"] = after_id

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT m.id, m.conversation_id, m.direction, m.message_text,
                   m.admin_user_id, m.admin_display_name, m.wa_message_id, m.created_at,
                   m.media_path, m.media_mime_type, m.media_filename, m.media_size,
                   m.original_message_text, m.edited_at, m.edited_by_admin_user_id
            FROM cc_messages m
            WHERE m.conversation_id = %(conv)s {after_clause}
            ORDER BY m.created_at ASC
            LIMIT %(limit)s
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_cc_message(message_id: int) -> Optional[dict]:
    """Fetch one Call Center message."""
    _ensure_cc_messages_media_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, conversation_id, direction, message_text,
                   admin_user_id, admin_display_name, wa_message_id, created_at,
                   media_path, media_mime_type, media_filename, media_size,
                   original_message_text, edited_at, edited_by_admin_user_id
            FROM cc_messages
            WHERE id = %(id)s
            """,
            {"id": message_id},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def update_cc_message_text(
    message_id: int,
    message_text: str,
    edited_by_admin_user_id: Optional[int] = None,
) -> Optional[dict]:
    """Update an outbound Call Center message text and retain its first text."""
    _ensure_cc_messages_media_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE cc_messages
            SET original_message_text = COALESCE(original_message_text, message_text),
                message_text = %(message_text)s,
                edited_at = NOW(),
                edited_by_admin_user_id = %(edited_by)s
            WHERE id = %(id)s AND direction = 'outbound'
            RETURNING id, conversation_id, direction, message_text,
                      admin_user_id, admin_display_name, wa_message_id, created_at,
                      media_path, media_mime_type, media_filename, media_size,
                      original_message_text, edited_at, edited_by_admin_user_id
            """,
            {
                "id": message_id,
                "message_text": message_text,
                "edited_by": edited_by_admin_user_id,
            },
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE cc_conversations
                SET updated_at = NOW()
                WHERE id = %(conv)s
                """,
                {"conv": row["conversation_id"]},
            )
    return dict(row) if row else None


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
                media_path TEXT,
                media_mime_type TEXT,
                media_filename TEXT,
                media_size INTEGER,
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
            ALTER TABLE cc_message_drafts
            ADD COLUMN IF NOT EXISTS media_path TEXT,
            ADD COLUMN IF NOT EXISTS media_mime_type TEXT,
            ADD COLUMN IF NOT EXISTS media_filename TEXT,
            ADD COLUMN IF NOT EXISTS media_size INTEGER
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
            SELECT d.id, d.admin_user_id, d.title, d.category, d.message_text,
                   d.media_path, d.media_mime_type, d.media_filename, d.media_size,
                   d.pinned, d.created_at, d.updated_at
                 , COALESCE(du.usage_count, 0) AS usage_count
            FROM cc_message_drafts d
            LEFT JOIN draft_usage du ON du.target_id = d.id
            WHERE d.admin_user_id = %(admin_user_id)s {category_clause}
            ORDER BY d.pinned DESC, COALESCE(du.usage_count, 0) DESC, d.updated_at DESC, d.id DESC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def get_cc_message_draft(draft_id: int, admin_user_id: int) -> Optional[dict]:
    _ensure_cc_message_drafts_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, admin_user_id, title, category, message_text,
                   media_path, media_mime_type, media_filename, media_size,
                   pinned, created_at, updated_at
            FROM cc_message_drafts
            WHERE id = %(draft_id)s AND admin_user_id = %(admin_user_id)s
            """,
            {"draft_id": draft_id, "admin_user_id": admin_user_id},
        )
        row = cur.fetchone()
    return dict(row) if row else None


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
    media_path: Optional[str] = None,
    media_mime_type: Optional[str] = None,
    media_filename: Optional[str] = None,
    media_size: Optional[int] = None,
) -> dict:
    _ensure_cc_message_drafts_schema()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO cc_message_drafts (
                admin_user_id, title, category, message_text,
                media_path, media_mime_type, media_filename, media_size,
                pinned, updated_at
            )
            VALUES (
                %(admin_user_id)s, %(title)s, %(category)s, %(message_text)s,
                %(media_path)s, %(media_mime_type)s, %(media_filename)s, %(media_size)s,
                FALSE, NOW()
            )
            RETURNING id, admin_user_id, title, category, message_text,
                      media_path, media_mime_type, media_filename, media_size,
                      pinned, created_at, updated_at
            """,
            {
                "admin_user_id": admin_user_id,
                "title": title,
                "category": category,
                "message_text": message_text,
                "media_path": media_path,
                "media_mime_type": media_mime_type,
                "media_filename": media_filename,
                "media_size": media_size,
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
    media_path: Optional[str] = None,
    media_mime_type: Optional[str] = None,
    media_filename: Optional[str] = None,
    media_size: Optional[int] = None,
    update_media: bool = False,
) -> Optional[dict]:
    _ensure_cc_message_drafts_schema()
    media_set_clause = ""
    params = {
        "draft_id": draft_id,
        "admin_user_id": admin_user_id,
        "title": title,
        "category": category,
        "message_text": message_text,
    }
    if update_media:
        media_set_clause = """
                media_path = %(media_path)s,
                media_mime_type = %(media_mime_type)s,
                media_filename = %(media_filename)s,
                media_size = %(media_size)s,
        """
        params.update(
            {
                "media_path": media_path,
                "media_mime_type": media_mime_type,
                "media_filename": media_filename,
                "media_size": media_size,
            }
        )

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            UPDATE cc_message_drafts
            SET title = %(title)s,
                category = %(category)s,
                message_text = %(message_text)s,
                {media_set_clause}
                updated_at = NOW()
            WHERE id = %(draft_id)s AND admin_user_id = %(admin_user_id)s
            RETURNING id, admin_user_id, title, category, message_text,
                      media_path, media_mime_type, media_filename, media_size,
                      pinned, created_at, updated_at
            """,
            params,
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
            WHERE id = %(draft_id)s AND admin_user_id = %(admin_user_id)s
            RETURNING id, admin_user_id, title, category, message_text,
                      media_path, media_mime_type, media_filename, media_size,
                      pinned, created_at, updated_at
            """,
            {"draft_id": draft_id, "admin_user_id": admin_user_id},
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


# ---------------------------------------------------------------------------
# Media Manager
# ---------------------------------------------------------------------------

def fetch_cc_media_db_refs(paths: list[str]) -> list[dict]:
    """Return DB rows that reference any of the given relative media paths.

    Each row has: table, id, media_path.
    """
    if not paths:
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 'cc_messages' AS tbl, id, media_path
            FROM cc_messages
            WHERE media_path = ANY(%(paths)s)
            UNION ALL
            SELECT 'cc_message_drafts' AS tbl, id, media_path
            FROM cc_message_drafts
            WHERE media_path = ANY(%(paths)s)
            """,
            {"paths": paths},
        )
        return [dict(r) for r in cur.fetchall()]


def clear_cc_media_db_refs(paths: list[str]) -> int:
    """Null-out media columns in cc_messages and cc_message_drafts for the given paths.

    Returns the total number of rows updated.
    """
    if not paths:
        return 0
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE cc_messages
            SET media_path = NULL,
                media_mime_type = NULL,
                media_filename = NULL,
                media_size = NULL
            WHERE media_path = ANY(%(paths)s)
            """,
            {"paths": paths},
        )
        messages_updated = cur.rowcount
        cur.execute(
            """
            UPDATE cc_message_drafts
            SET media_path = NULL,
                media_mime_type = NULL,
                media_filename = NULL,
                media_size = NULL
            WHERE media_path = ANY(%(paths)s)
            """,
            {"paths": paths},
        )
        drafts_updated = cur.rowcount
    return messages_updated + drafts_updated


def _escape_md(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    for ch in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(ch, f"\\{ch}")
    return text
