from __future__ import annotations

import logging
import platform
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from dashboard.db_access import get_cursor

DEFAULT_SYSTEM_SETTINGS = [
    # General Settings
    {
        "setting_key": "app_name",
        "setting_value": "Dashboard SUDIN ASKA",
        "category": "general",
        "description": "Nama utama aplikasi dashboard",
        "is_secret": False,
    },
    {
        "setting_key": "app_subtitle",
        "setting_value": "Sistem Informasi & Layanan Terpadu Suku Dinas Pendidikan",
        "category": "general",
        "description": "Sub-judul / tagline portal",
        "is_secret": False,
    },
    {
        "setting_key": "organization_name",
        "setting_value": "Suku Dinas Pendidikan Wilayah 1 Jakarta Utara",
        "category": "general",
        "description": "Nama instansi / organisasi pengelola",
        "is_secret": False,
    },
    {
        "setting_key": "support_email",
        "setting_value": "support@sudinaska.id",
        "category": "general",
        "description": "Email kontak bantuan teknis",
        "is_secret": False,
    },
    {
        "setting_key": "support_phone",
        "setting_value": "021-43930000",
        "category": "general",
        "description": "Nomor telepon / WhatsApp hotline",
        "is_secret": False,
    },
    {
        "setting_key": "maintenance_mode",
        "setting_value": "false",
        "category": "general",
        "description": "Mode pemeliharaan sistem (true/false)",
        "is_secret": False,
    },
    {
        "setting_key": "maintenance_message",
        "setting_value": "Sistem sedang dalam pemeliharaan berkala. Silakan kembali beberapa saat lagi.",
        "category": "general",
        "description": "Pesan yang ditampilkan saat mode pemeliharaan aktif",
        "is_secret": False,
    },
    {
        "setting_key": "session_timeout_minutes",
        "setting_value": "120",
        "category": "general",
        "description": "Durasi batas waktu sesi inaktif (dalam menit)",
        "is_secret": False,
    },
    {
        "setting_key": "allow_user_registration",
        "setting_value": "false",
        "category": "general",
        "description": "Izinkan registrasi pengguna baru secara mandiri",
        "is_secret": False,
    },
    # Notification Settings
    {
        "setting_key": "telegram_notifications_enabled",
        "setting_value": "true",
        "category": "notification",
        "description": "Status pengiriman notifikasi Telegram",
        "is_secret": False,
    },
    {
        "setting_key": "telegram_bot_token",
        "setting_value": "",
        "category": "notification",
        "description": "Token Bot Telegram untuk notifikasi sistem",
        "is_secret": True,
    },
    {
        "setting_key": "telegram_chat_id",
        "setting_value": "",
        "category": "notification",
        "description": "ID Chat / Grup Telegram penerima notifikasi",
        "is_secret": False,
    },
    {
        "setting_key": "whatsapp_notifications_enabled",
        "setting_value": "true",
        "category": "notification",
        "description": "Status notifikasi via WhatsApp Gateway",
        "is_secret": False,
    },
    {
        "setting_key": "email_notifications_enabled",
        "setting_value": "false",
        "category": "notification",
        "description": "Status pengiriman email notifikasi",
        "is_secret": False,
    },
    {
        "setting_key": "notify_on_new_login",
        "setting_value": "true",
        "category": "notification",
        "description": "Kirim notifikasi saat ada login admin baru",
        "is_secret": False,
    },
    {
        "setting_key": "notify_on_system_error",
        "setting_value": "true",
        "category": "notification",
        "description": "Kirim alert notifikasi jika terjadi error kritis sistem",
        "is_secret": False,
    },
    {
        "setting_key": "notify_daily_summary",
        "setting_value": "true",
        "category": "notification",
        "description": "Kirim ringkasan statistik harian",
        "is_secret": False,
    },
    # API Settings
    {
        "setting_key": "openai_api_key",
        "setting_value": "",
        "category": "api",
        "description": "API Key OpenAI untuk fitur kecerdasan/AI",
        "is_secret": True,
    },
    {
        "setting_key": "gemini_api_key",
        "setting_value": "",
        "category": "api",
        "description": "API Key Google Gemini AI",
        "is_secret": True,
    },
    {
        "setting_key": "whatsapp_api_endpoint",
        "setting_value": "",
        "category": "api",
        "description": "URL Endpoint WhatsApp Gateway API",
        "is_secret": False,
    },
    {
        "setting_key": "whatsapp_api_key",
        "setting_value": "",
        "category": "api",
        "description": "API Key WhatsApp Gateway",
        "is_secret": True,
    },
    {
        "setting_key": "telegram_webhook_url",
        "setting_value": "",
        "category": "api",
        "description": "URL Webhook Telegram Bot",
        "is_secret": False,
    },
    {
        "setting_key": "api_rate_limit_per_min",
        "setting_value": "60",
        "category": "api",
        "description": "Batas maksimum panggilan API per menit",
        "is_secret": False,
    },
    {
        "setting_key": "api_access_enabled",
        "setting_value": "true",
        "category": "api",
        "description": "Status akses API eksternal",
        "is_secret": False,
    },
]


def ensure_default_system_settings() -> None:
    """Ensure system_settings table has default settings populated."""
    try:
        with get_cursor(commit=True) as cur:
            for item in DEFAULT_SYSTEM_SETTINGS:
                cur.execute(
                    """
                    INSERT INTO system_settings (setting_key, setting_value, category, description, is_secret)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (setting_key) DO NOTHING;
                    """,
                    (
                        item["setting_key"],
                        item["setting_value"],
                        item["category"],
                        item["description"],
                        item["is_secret"],
                    ),
                )
    except Exception as exc:
        logging.warning("Error ensuring default system settings: %s", exc)


def get_all_system_settings() -> Dict[str, Dict[str, Any]]:
    """Retrieve all system settings mapped by setting_key."""
    ensure_default_system_settings()
    results: Dict[str, Dict[str, Any]] = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT setting_key, setting_value, category, description, is_secret, updated_at, updated_by
                FROM system_settings
                ORDER BY category, setting_key;
                """
            )
            rows = cur.fetchall()
            for row in rows:
                key = row["setting_key"]
                results[key] = {
                    "setting_key": key,
                    "setting_value": row["setting_value"] or "",
                    "category": row["category"],
                    "description": row["description"] or "",
                    "is_secret": bool(row["is_secret"]),
                    "updated_at": row["updated_at"],
                    "updated_by": row["updated_by"],
                }
    except Exception as exc:
        logging.warning("Error fetching system settings: %s", exc)
        for item in DEFAULT_SYSTEM_SETTINGS:
            results[item["setting_key"]] = {
                "setting_key": item["setting_key"],
                "setting_value": item["setting_value"],
                "category": item["category"],
                "description": item["description"],
                "is_secret": item["is_secret"],
                "updated_at": None,
                "updated_by": None,
            }
    return results


def get_system_settings_dict() -> Dict[str, str]:
    """Get key -> string value mapping of all system settings."""
    settings = get_all_system_settings()
    return {k: v["setting_value"] for k, v in settings.items()}


def get_system_setting(key: str, default: str = "") -> str:
    """Get single system setting value by key."""
    settings = get_system_settings_dict()
    return settings.get(key, default)


def update_system_settings(settings_data: Dict[str, str], user_id: Optional[int] = None) -> bool:
    """Batch update system settings from key-value dictionary."""
    ensure_default_system_settings()
    if not settings_data:
        return True
    try:
        with get_cursor(commit=True) as cur:
            for key, val in settings_data.items():
                cur.execute(
                    """
                    INSERT INTO system_settings (setting_key, setting_value, updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT (setting_key) DO UPDATE
                    SET setting_value = EXCLUDED.setting_value,
                        updated_at = NOW(),
                        updated_by = EXCLUDED.updated_by;
                    """,
                    (key, str(val), user_id),
                )
        return True
    except Exception as exc:
        logging.error("Error updating system settings: %s", exc)
        return False


def get_system_diagnostic_info() -> Dict[str, Any]:
    """Get system health and diagnostic information for settings page."""
    info = {
        "db_connected": False,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "total_users": 0,
        "admin_users": 0,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
    }
    try:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM dashboard_users;")
            res = cur.fetchone()
            info["total_users"] = res["total"] if res else 0

            cur.execute("SELECT COUNT(*) AS total FROM dashboard_users WHERE role = 'admin';")
            res_admin = cur.fetchone()
            info["admin_users"] = res_admin["total"] if res_admin else 0
            info["db_connected"] = True
    except Exception:
        info["db_connected"] = False

    return info


# ===== PUBLIC API KEY QUERIES =====

import json
import secrets
from psycopg2.extras import Json


def list_public_api_keys() -> List[Dict[str, Any]]:
    """List all public API keys with creator information."""
    results: List[Dict[str, Any]] = []
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT k.id, k.client_name, k.contact_email, k.api_key, k.scopes, k.is_active, k.notes,
                       k.last_used_at, k.created_at, k.created_by,
                       u.full_name AS created_by_name, u.email AS created_by_email
                FROM public_api_keys k
                LEFT JOIN dashboard_users u ON u.id = k.created_by
                ORDER BY k.created_at DESC;
                """
            )
            rows = cur.fetchall()
            for row in rows:
                scopes_list = row["scopes"]
                if isinstance(scopes_list, str):
                    try:
                        scopes_list = json.loads(scopes_list)
                    except Exception:
                        scopes_list = ["schools:read"]
                results.append({
                    "id": row["id"],
                    "client_name": row["client_name"],
                    "contact_email": row["contact_email"] or "",
                    "api_key": row["api_key"],
                    "scopes": scopes_list or ["schools:read"],
                    "is_active": bool(row["is_active"]),
                    "notes": row["notes"] or "",
                    "last_used_at": row["last_used_at"],
                    "created_at": row["created_at"],
                    "created_by": row["created_by"],
                    "created_by_name": row["created_by_name"] or row["created_by_email"] or "-",
                })
    except Exception as exc:
        logging.error("Error fetching public API keys: %s", exc)
    return results


def create_public_api_key(
    client_name: str,
    contact_email: str = "",
    scopes: Optional[List[str]] = None,
    notes: str = "",
    created_by: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Generate and store a new public API Key."""
    if not client_name:
        return None

    if not scopes:
        scopes = ["schools:read"]

    # Generate a secure token string, e.g. pk_live_3f8b9...
    raw_key = f"pk_live_{secrets.token_hex(20)}"

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO public_api_keys (client_name, contact_email, api_key, scopes, notes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, client_name, contact_email, api_key, scopes, is_active, created_at;
                """,
                (client_name, contact_email, raw_key, Json(scopes), notes, created_by),
            )
            res = cur.fetchone()
            if res:
                return dict(res)
    except Exception as exc:
        logging.error("Error creating public API key: %s", exc)
    return None


def toggle_public_api_key_status(key_id: int) -> bool:
    """Toggle active status of a public API key."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE public_api_keys
                SET is_active = NOT is_active
                WHERE id = %s;
                """,
                (key_id,),
            )
            return cur.rowcount > 0
    except Exception as exc:
        logging.error("Error toggling public API key status: %s", exc)
        return False


def delete_public_api_key(key_id: int) -> bool:
    """Delete a public API key by ID."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM public_api_keys WHERE id = %s;", (key_id,))
            return cur.rowcount > 0
    except Exception as exc:
        logging.error("Error deleting public API key: %s", exc)
        return False


def verify_public_api_key(api_key: str, required_scope: str = "schools:read") -> Optional[Dict[str, Any]]:
    """Validate public API key and check if required scope is enabled."""
    if not api_key:
        return None

    clean_key = api_key.strip()
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT id, client_name, contact_email, api_key, scopes, is_active
                FROM public_api_keys
                WHERE api_key = %s AND is_active = TRUE;
                """,
                (clean_key,),
            )
            row = cur.fetchone()
            if not row:
                return None

            scopes_list = row["scopes"]
            if isinstance(scopes_list, str):
                try:
                    scopes_list = json.loads(scopes_list)
                except Exception:
                    scopes_list = ["schools:read"]

            if required_scope not in (scopes_list or []):
                return None

            # Update last_used_at timestamp
            cur.execute(
                "UPDATE public_api_keys SET last_used_at = NOW() WHERE id = %s;",
                (row["id"],),
            )
            return dict(row)
    except Exception as exc:
        logging.error("Error verifying public API key: %s", exc)
        return None


def fetch_public_schools_api_data() -> List[Dict[str, Any]]:
    """Fetch active school data formatted for public API consumption."""
    results: List[Dict[str, Any]] = []
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, npsn, name, jenjang, status, address, phone, logo_url, updated_at
                FROM portal_schools
                WHERE active = TRUE
                ORDER BY jenjang, name;
                """
            )
            rows = cur.fetchall()
            for r in rows:
                results.append({
                    "id": r["id"],
                    "npsn": r["npsn"] or "",
                    "name": r["name"] or "",
                    "jenjang": r["jenjang"] or "SD",
                    "status": r["status"] or "NEGERI",
                    "address": r["address"] or "",
                    "phone": r["phone"] or "",
                    "logo_url": r["logo_url"] or "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] and hasattr(r["updated_at"], "isoformat") else None,
                })
    except Exception as exc:
        logging.error("Error fetching public schools API data: %s", exc)
    return results

