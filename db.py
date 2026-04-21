from __future__ import annotations

import os
import random
import re
import secrets
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import extensions, InterfaceError, OperationalError, ProgrammingError, IntegrityError
from psycopg2.extras import Json, RealDictCursor
from dotenv import load_dotenv
from account_status import ACCOUNT_STATUS_CHOICES, ACCOUNT_STATUS_ACTIVE

# Muat variabel dari file .env
load_dotenv()


def _normalize_db_host(value: str | None) -> str | None:
    clean = (value or "").strip()
    if not clean:
        return clean
    if clean.lower() == "localhost":
        return "127.0.0.1"
    return clean

# Ambil variabel koneksi dari environment
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_SSLMODE = os.getenv("DB_SSLMODE")  # Optional: hanya dipakai jika ada

# Validasi agar semua variabel penting ada
required_vars = {
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASS": DB_PASS,
    "DB_HOST": DB_HOST,
    "DB_PORT": DB_PORT,
}
for key, value in required_vars.items():
    if not value:
        raise ValueError(
            f"Environment variable '{key}' is not set! Silakan isi di file .env Anda."
        )

# Siapkan argumen koneksi
conn_args = dict(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASS,
    host=_normalize_db_host(DB_HOST),
    port=DB_PORT,
)

# Tambahkan sslmode jika diset di .env
if DB_SSLMODE:
    conn_args["sslmode"] = DB_SSLMODE

# Koneksi ke PostgreSQL
conn = psycopg2.connect(**conn_args)

_CHAT_TOPIC_AVAILABLE: Optional[bool] = None
_CHAT_CHANNEL_AVAILABLE: Optional[bool] = None
MAX_TWITTER_LOG_ROWS = max(0, int(os.getenv("TWITTER_LOG_MAX_ROWS", "100") or 100))
DEFAULT_LIMITED_QUOTA = 20
LIMIT_COOLDOWN_HOURS = 24
DEFAULT_LIMITED_REASON = (
    f"Akses Gmail: maksimal {DEFAULT_LIMITED_QUOTA} chat per 24 jam. "
    "Kalau mau unlimited, pakai akun belajar.id atau Telegram."
)
STATUS_ENUM_SQL = ", ".join(f"'{status}'" for status in ACCOUNT_STATUS_CHOICES)
CHAT_CHANNEL_EXPRESSION = (
    "COALESCE(channel, CASE WHEN topic = 'web' THEN 'web' "
    "WHEN topic = 'twitter' THEN 'twitter' "
    "WHEN topic = 'whatsapp' THEN 'whatsapp' ELSE 'telegram' END)"
)
def _chat_logs_has_topic_column(force_refresh: bool = False) -> bool:
    """
    Periksa sekali apakah tabel chat_logs memiliki kolom 'topic'.
    Hasil dicegah supaya query berikutnya lebih cepat dan stabil.
    """
    global _CHAT_TOPIC_AVAILABLE
    if _CHAT_TOPIC_AVAILABLE is not None and not force_refresh:
        return _CHAT_TOPIC_AVAILABLE

    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'chat_logs'
          AND column_name = 'topic'
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query)
        _CHAT_TOPIC_AVAILABLE = cur.fetchone() is not None
    return _CHAT_TOPIC_AVAILABLE


def _chat_logs_has_channel_column(force_refresh: bool = False) -> bool:
    """Cek keberadaan kolom channel pada chat_logs."""
    global _CHAT_CHANNEL_AVAILABLE
    if _CHAT_CHANNEL_AVAILABLE is not None and not force_refresh:
        return _CHAT_CHANNEL_AVAILABLE

    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'chat_logs'
          AND column_name = 'channel'
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query)
        _CHAT_CHANNEL_AVAILABLE = cur.fetchone() is not None
    return _CHAT_CHANNEL_AVAILABLE

def _ensure_chat_logs_schema() -> None:
    """Pastikan tabel chat_logs dan semua kolomnya tersedia."""
    global _CHAT_TOPIC_AVAILABLE, _CHAT_CHANNEL_AVAILABLE
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                text TEXT,
                role TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                response_time_ms INTEGER
            );
            """
        )
        # Tambahkan kolom 'topic' jika belum ada, untuk menjaga kompatibilitas
        if not _chat_logs_has_topic_column(force_refresh=True):
            cur.execute("ALTER TABLE chat_logs ADD COLUMN topic TEXT")
            _CHAT_TOPIC_AVAILABLE = True  # Update cache
        if not _chat_logs_has_channel_column(force_refresh=True):
            cur.execute("ALTER TABLE chat_logs ADD COLUMN channel TEXT")
            cur.execute(
                """
                UPDATE chat_logs
                SET channel = CASE
                    WHEN topic = 'web' THEN 'web'
                    WHEN topic = 'twitter' THEN 'twitter'
                    WHEN topic = 'whatsapp' THEN 'whatsapp'
                    ELSE 'telegram'
                END
                WHERE channel IS NULL
                """
            )
            cur.execute("ALTER TABLE chat_logs ALTER COLUMN channel SET DEFAULT 'telegram'")
            _CHAT_CHANNEL_AVAILABLE = True
        else:
            cur.execute(
                """
                UPDATE chat_logs
                SET channel = CASE
                    WHEN topic = 'web' THEN 'web'
                    WHEN topic = 'twitter' THEN 'twitter'
                    WHEN topic = 'whatsapp' THEN 'whatsapp'
                    ELSE 'telegram'
                END
                WHERE channel IS NULL
                """
            )
    conn.commit()

def _ensure_bullying_schema() -> None:
    """Pastikan tabel dan kolom pendukung pelaporan bullying tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bullying_reports (
                id SERIAL PRIMARY KEY,
                chat_log_id INTEGER UNIQUE REFERENCES chat_logs(id) ON DELETE CASCADE,
                user_id BIGINT,
                username TEXT,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority BOOLEAN NOT NULL DEFAULT TRUE,
                notes TEXT,
                last_updated_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                category TEXT NOT NULL DEFAULT 'general',
                severity TEXT,
                metadata JSONB,
                assigned_to TEXT,
                due_at TIMESTAMPTZ,
                resolved_at TIMESTAMPTZ,
                escalated BOOLEAN NOT NULL DEFAULT FALSE,
                CONSTRAINT bullying_reports_status_check CHECK (status IN ('pending', 'in_progress', 'resolved', 'spam'))
            );
            """
        )
    conn.commit()

def _ensure_psych_schema() -> None:
    """Pastikan tabel laporan konseling psikologis tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS psych_reports (
                id SERIAL PRIMARY KEY,
                chat_log_id INTEGER REFERENCES chat_logs(id) ON DELETE SET NULL,
                user_id BIGINT,
                username TEXT,
                message TEXT NOT NULL,
                summary TEXT,
                severity TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'open',
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK (status IN ('open', 'in_progress', 'resolved', 'archived'))
            );
            """
        )
    conn.commit()


def _reset_chat_logs_sequence() -> None:
    """Reset chat_logs id sequence to max(id) to avoid duplicate PK errors."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_get_serial_sequence('chat_logs', 'id')")
        row = cur.fetchone()
        seq_name = row[0] if row else None
        if not seq_name:
            return
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM chat_logs")
        max_id = cur.fetchone()[0] or 0
        cur.execute("SELECT setval(%s, %s, %s)", (seq_name, max_id, True))
    conn.commit()


def _ensure_feedback_schema() -> None:
    """Pastikan tabel chat_feedback tersedia untuk menyimpan feedback like/dislike."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_feedback (
                id SERIAL PRIMARY KEY,
                chat_log_id INTEGER NOT NULL REFERENCES chat_logs(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                username TEXT,
                feedback_type TEXT NOT NULL CHECK (feedback_type IN ('like', 'dislike')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (chat_log_id, user_id)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_feedback_chat_log 
            ON chat_feedback (chat_log_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_feedback_user 
            ON chat_feedback (user_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_feedback_type 
            ON chat_feedback (feedback_type);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_feedback_created 
            ON chat_feedback (created_at DESC);
            """
        )
    conn.commit()


def _ensure_connection() -> None:
    global conn
    try:
        if conn is None or conn.closed != 0:
            conn = psycopg2.connect(**conn_args)
    except Exception:
        conn = psycopg2.connect(**conn_args)


def _column_exists(table: str, column: str) -> bool:
    _ensure_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
            return cur.fetchone() is not None
    except InterfaceError:
        _ensure_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
            return cur.fetchone() is not None


def _normalize_phone(phone: Optional[str]) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return digits


def _table_exists(table: str) -> bool:
    _ensure_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = %s
                LIMIT 1
                """,
                (table,),
            )
            return cur.fetchone() is not None
    except InterfaceError:
        _ensure_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = %s
                LIMIT 1
                """,
                (table,),
            )
            return cur.fetchone() is not None


def _ensure_column(table: str, column: str, ddl: str) -> bool:
    if _column_exists(table, column):
        return False
    _ensure_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        conn.commit()
    except InterfaceError:
        _ensure_connection()
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        conn.commit()
    return True


def _constraint_exists(table: str, constraint: str) -> bool:
    _ensure_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND constraint_name = %s
                LIMIT 1
                """,
                (table, constraint),
            )
            return cur.fetchone() is not None
    except InterfaceError:
        _ensure_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND constraint_name = %s
                LIMIT 1
                """,
                (table, constraint),
            )
            return cur.fetchone() is not None


def save_feedback(
    chat_log_id: int,
    user_id: int,
    username: Optional[str],
    feedback_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Simpan atau update feedback untuk chat message.

    Args:
        chat_log_id: ID dari chat_logs yang diberi feedback
        user_id: ID user yang memberikan feedback
        username: Username untuk display purposes
        feedback_type: 'like' atau 'dislike'

    Returns:
        Dict dengan feedback data jika berhasil, None jika gagal

    Raises:
        ValueError: Jika feedback_type tidak valid
        psycopg2.IntegrityError: Jika chat_log_id tidak ada (foreign key violation)
    """
    _ensure_feedback_schema()

    if feedback_type not in ("like", "dislike"):
        raise ValueError(f"Invalid feedback_type: {feedback_type}. Must be 'like' or 'dislike'")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO chat_feedback (
                    chat_log_id,
                    user_id,
                    username,
                    feedback_type,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (chat_log_id, user_id)
                DO UPDATE SET
                    feedback_type = EXCLUDED.feedback_type,
                    updated_at = NOW()
                RETURNING
                    id,
                    chat_log_id,
                    user_id,
                    username,
                    feedback_type,
                    created_at,
                    updated_at
                """,
                (chat_log_id, user_id, username, feedback_type),
            )
            result = cur.fetchone()
        conn.commit()
        return dict(result) if result else None
    except psycopg2.IntegrityError as exc:
        conn.rollback()
        if "chat_logs" in str(exc):
            raise ValueError(f"chat_log_id {chat_log_id} does not exist")
        raise


def delete_feedback(chat_log_id: int, user_id: int) -> bool:
    """
    Hapus feedback untuk chat message tertentu dari user tertentu.

    Args:
        chat_log_id: ID dari chat_logs
        user_id: ID user yang memberikan feedback

    Returns:
        True jika feedback dihapus, False jika tidak ditemukan
    """
    _ensure_feedback_schema()

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM chat_feedback
            WHERE chat_log_id = %s AND user_id = %s
            """,
            (chat_log_id, user_id),
        )
        deleted_count = cur.rowcount
    conn.commit()
    return deleted_count > 0


def get_feedback_status(chat_log_ids: List[int], user_id: int) -> Dict[int, Optional[Dict[str, Any]]]:
    """
    Ambil status feedback untuk multiple chat messages dari user tertentu.

    Args:
        chat_log_ids: List of chat_log_id yang ingin dicek
        user_id: ID user yang memberikan feedback

    Returns:
        Dict mapping chat_log_id ke feedback data (atau None jika tidak ada feedback)
    """
    if not chat_log_ids:
        return {}

    _ensure_feedback_schema()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                chat_log_id,
                feedback_type,
                created_at,
                updated_at
            FROM chat_feedback
            WHERE chat_log_id = ANY(%s) AND user_id = %s
            """,
            (chat_log_ids, user_id),
        )
        rows = cur.fetchall()

    result = {cid: None for cid in chat_log_ids}
    for row in rows:
        result[row["chat_log_id"]] = {
            "feedback_type": row["feedback_type"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    return result


def get_feedback_by_chat_log(chat_log_id: int) -> List[Dict[str, Any]]:
    """
    Ambil semua feedback untuk chat message tertentu (dari semua user).

    Args:
        chat_log_id: ID dari chat_logs

    Returns:
        List of feedback records
    """
    _ensure_feedback_schema()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id,
                chat_log_id,
                user_id,
                username,
                feedback_type,
                created_at,
                updated_at
            FROM chat_feedback
            WHERE chat_log_id = %s
            ORDER BY created_at DESC
            """,
            (chat_log_id,),
        )
        rows = cur.fetchall()

    return [dict(row) for row in rows]


def _ensure_user_schema() -> None:
    """Pastikan tabel untuk pengguna web (web_users) tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT,
                photo_url TEXT,
                last_login TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                auth_provider TEXT,
                access_tier TEXT NOT NULL DEFAULT 'full',
                quota_limit INTEGER,
                quota_remaining INTEGER,
                quota_reset_at TIMESTAMPTZ,
                limited_reason TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                status_reason TEXT,
                status_changed_at TIMESTAMPTZ,
                status_changed_by TEXT,
                metadata JSONB,
                CONSTRAINT web_users_status_check CHECK (status IN (%s))
            );
            """
            % STATUS_ENUM_SQL
        )
    conn.commit()
    # Tambahkan kolom baru jika belum ada (untuk versi lama)
    altered = False
    altered |= _ensure_column(
        "web_users",
        "auth_provider",
        "auth_provider TEXT",
    )
    altered |= _ensure_column(
        "web_users",
        "access_tier",
        "access_tier TEXT NOT NULL DEFAULT 'full'",
    )
    altered |= _ensure_column(
        "web_users",
        "quota_limit",
        "quota_limit INTEGER",
    )
    altered |= _ensure_column(
        "web_users",
        "quota_remaining",
        "quota_remaining INTEGER",
    )
    altered |= _ensure_column(
        "web_users",
        "quota_reset_at",
        "quota_reset_at TIMESTAMPTZ",
    )
    altered |= _ensure_column(
        "web_users",
        "limited_reason",
        "limited_reason TEXT",
    )
    altered |= _ensure_column(
        "web_users",
        "status",
        f"status TEXT NOT NULL DEFAULT '{ACCOUNT_STATUS_ACTIVE}'",
    )
    altered |= _ensure_column(
        "web_users",
        "status_reason",
        "status_reason TEXT",
    )
    altered |= _ensure_column(
        "web_users",
        "status_changed_at",
        "status_changed_at TIMESTAMPTZ",
    )
    altered |= _ensure_column(
        "web_users",
        "status_changed_by",
        "status_changed_by TEXT",
    )
    altered |= _ensure_column(
        "web_users",
        "metadata",
        "metadata JSONB",
    )
    if altered:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE web_users
                SET access_tier = COALESCE(access_tier, 'full')
                """
            )
        conn.commit()
    if not _constraint_exists("web_users", "web_users_status_check"):
        with conn.cursor() as cur:
            cur.execute(
                f"""
                ALTER TABLE web_users
                ADD CONSTRAINT web_users_status_check
                CHECK (status IN ({STATUS_ENUM_SQL}))
                """
            )
        conn.commit()


def _ensure_guestbook_general_schema() -> None:
    """Pastikan tabel buku tamu umum (web) tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daftar_tamu_general_transactions (
                id SERIAL PRIMARY KEY,
                school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
                visit_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                purpose TEXT,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                reviewed_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMPTZ,
                reviewer_notes TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_school
            ON daftar_tamu_general_transactions (school_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_status
            ON daftar_tamu_general_transactions (status);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transactions_visit_at
            ON daftar_tamu_general_transactions (visit_at DESC);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daftar_tamu_general_transaction_guests (
                id SERIAL PRIMARY KEY,
                transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_general_transactions(id) ON DELETE CASCADE,
                general_guest_id INTEGER REFERENCES daftar_tamu_general_guests(id) ON DELETE SET NULL,
                full_name TEXT NOT NULL,
                phone TEXT,
                instansi TEXT,
                jabatan TEXT,
                email TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transaction_guests_tx
            ON daftar_tamu_general_transaction_guests (transaction_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_general_transaction_guests_guest
            ON daftar_tamu_general_transaction_guests (general_guest_id);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daftar_tamu_purpose_keywords (
                id SERIAL PRIMARY KEY,
                keyword TEXT NOT NULL UNIQUE,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_purpose_keywords_active
            ON daftar_tamu_purpose_keywords (active);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_purpose_keywords_keyword
            ON daftar_tamu_purpose_keywords (lower(keyword));
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daftar_tamu_contact_priority (
                id SERIAL PRIMARY KEY,
                contact_key TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daftar_tamu_contact_priority_active
            ON daftar_tamu_contact_priority (active);
            """
        )
    conn.commit()
    if _table_exists("daftar_tamu_general_guests"):
        _ensure_column("daftar_tamu_general_guests", "email", "email TEXT")
        _ensure_column(
            "daftar_tamu_general_guests",
            "is_parent",
            "is_parent BOOLEAN NOT NULL DEFAULT FALSE",
        )
        _ensure_column(
            "daftar_tamu_general_guests",
            "student_class",
            "student_class TEXT",
        )
        _ensure_column(
            "daftar_tamu_general_guests",
            "student_name",
            "student_name TEXT",
        )
        _ensure_column(
            "daftar_tamu_general_guests",
            "is_deleted",
            "is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
        )
        _ensure_column(
            "daftar_tamu_general_guests",
            "deleted_by",
            "deleted_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL",
        )
        _ensure_column("daftar_tamu_general_guests", "deleted_at", "deleted_at TIMESTAMPTZ")
    if _table_exists("daftar_tamu_general_transaction_guests"):
        _ensure_column(
            "daftar_tamu_general_transaction_guests",
            "student_class",
            "student_class TEXT",
        )
        _ensure_column(
            "daftar_tamu_general_transaction_guests",
            "student_name",
            "student_name TEXT",
        )


def _ensure_guestbook_hospitality_schema() -> None:
    """Pastikan tabel review hospitality untuk buku tamu umum tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hospitality_guestbook_reviews (
                id SERIAL PRIMARY KEY,
                transaction_id INTEGER NOT NULL REFERENCES daftar_tamu_general_transactions(id) ON DELETE CASCADE,
                school_id INTEGER NOT NULL REFERENCES portal_schools(id) ON DELETE CASCADE,
                review_token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
                rating SMALLINT,
                comment TEXT,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT hospitality_guestbook_reviews_rating_check CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
            );
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hosp_guestbook_reviews_transaction
            ON hospitality_guestbook_reviews (transaction_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_school
            ON hospitality_guestbook_reviews (school_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_status
            ON hospitality_guestbook_reviews (status);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_guestbook_reviews_completed_at
            ON hospitality_guestbook_reviews (completed_at DESC);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_questions (
                id SERIAL PRIMARY KEY,
                question_text TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER REFERENCES dashboard_users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_extra_questions_active_order
            ON hospitality_guestbook_extra_questions (active, sort_order, id);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hospitality_guestbook_extra_answers (
                id SERIAL PRIMARY KEY,
                review_id INTEGER NOT NULL REFERENCES hospitality_guestbook_reviews(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES hospitality_guestbook_extra_questions(id) ON DELETE CASCADE,
                rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (review_id, question_id)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_review
            ON hospitality_guestbook_extra_answers (review_id);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hosp_extra_answers_question
            ON hospitality_guestbook_extra_answers (question_id);
            """
        )
    conn.commit()


def list_guestbook_purpose_keywords(*, active_only: bool = True, limit: int = 50) -> List[str]:
    _ensure_guestbook_general_schema()
    safe_limit = max(1, min(int(limit or 50), 500))

    where_sql = "WHERE active = TRUE" if active_only else ""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT keyword
            FROM daftar_tamu_purpose_keywords
            {where_sql}
            ORDER BY lower(keyword) ASC
            LIMIT %s
            """,
            (safe_limit,),
        )
        rows = cur.fetchall() or []
    keywords = []
    seen = set()
    for row in rows:
        kw = (row.get("keyword") or "").strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(kw)
    return keywords


def list_guestbook_contact_priorities(*, active_only: bool = True) -> List[str]:
    _ensure_guestbook_general_schema()
    defaults = [
        ("website", 1),
        ("email", 2),
        ("phone", 3),
        ("instagram", 4),
        ("wa_channel", 5),
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM daftar_tamu_contact_priority")
        total = cur.fetchone()[0] or 0
        if total == 0:
            for key, order in defaults:
                cur.execute(
                    """
                    INSERT INTO daftar_tamu_contact_priority (contact_key, sort_order, active)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (contact_key) DO NOTHING
                    """,
                    (key, order),
                )
    conn.commit()

    where_sql = "WHERE active = TRUE" if active_only else ""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT contact_key
            FROM daftar_tamu_contact_priority
            {where_sql}
            ORDER BY sort_order ASC, id ASC
            """
        )
        rows = cur.fetchall() or []
    return [row.get("contact_key") for row in rows if row.get("contact_key")]


def list_school_classroom_options(school_id: int) -> List[str]:
    _ensure_guestbook_general_schema()
    if not school_id:
        return []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT name
            FROM school_classrooms
            WHERE school_id = %s
              AND active = TRUE
            ORDER BY grade_level NULLS LAST, variant NULLS LAST, name ASC
            """,
            (school_id,),
        )
        rows = cur.fetchall() or []
    return [row.get("name") for row in rows if row.get("name")]


def _backfill_telegram_users() -> None:
    """Buat data user Telegram dari chat_logs jika table kosong/belum lengkap."""
    _ensure_chat_logs_schema()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO telegram_users (
                telegram_user_id,
                username,
                first_seen_at,
                last_seen_at
            )
            SELECT
                user_id,
                MAX(username) FILTER (WHERE username IS NOT NULL),
                MIN(created_at),
                MAX(created_at)
            FROM chat_logs
            WHERE user_id IS NOT NULL
              AND {CHAT_CHANNEL_EXPRESSION} = 'telegram'
            GROUP BY user_id
            ON CONFLICT (telegram_user_id) DO NOTHING
            """
        )
    conn.commit()


def _ensure_telegram_user_schema() -> None:
    """Pastikan tabel telegram_users tersedia dan terisi dari chat_logs."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS telegram_users (
                id SERIAL PRIMARY KEY,
                telegram_user_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_message_preview TEXT,
                status TEXT NOT NULL DEFAULT '{ACCOUNT_STATUS_ACTIVE}',
                status_reason TEXT,
                status_changed_at TIMESTAMPTZ,
                status_changed_by TEXT,
                metadata JSONB,
                CONSTRAINT telegram_users_status_check CHECK (status IN ({STATUS_ENUM_SQL}))
            );
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_users_user
            ON telegram_users (telegram_user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_telegram_users_status
            ON telegram_users (status)
            """
        )
    conn.commit()
    _backfill_telegram_users()


def _sync_telegram_user_profile(
    telegram_user_id: Optional[int],
    username: Optional[str],
    last_message: Optional[str],
) -> None:
    """Upsert profil telegram berdasarkan chat terbaru."""
    if not telegram_user_id:
        return
    _ensure_telegram_user_schema()
    clean_username = (username or "").strip() or None
    preview = (last_message or "").strip()
    if preview:
        preview = preview[:280]
    else:
        preview = None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO telegram_users (
                telegram_user_id,
                username,
                last_message_preview
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE
            SET
                username = COALESCE(EXCLUDED.username, telegram_users.username),
                last_seen_at = NOW(),
                last_message_preview = COALESCE(
                    EXCLUDED.last_message_preview,
                    telegram_users.last_message_preview
                )
            """,
            (telegram_user_id, clean_username, preview),
        )


def _backfill_whatsapp_users() -> None:
    """Buat data user WhatsApp dari chat_logs jika table kosong/belum lengkap."""
    _ensure_chat_logs_schema()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO whatsapp_users (
                whatsapp_user_id,
                display_name,
                first_seen_at,
                last_seen_at
            )
            SELECT
                user_id,
                MAX(username) FILTER (WHERE username IS NOT NULL),
                MIN(created_at),
                MAX(created_at)
            FROM chat_logs
            WHERE user_id IS NOT NULL
              AND {CHAT_CHANNEL_EXPRESSION} = 'whatsapp'
            GROUP BY user_id
            ON CONFLICT (whatsapp_user_id) DO NOTHING
            """
        )
    conn.commit()


def _ensure_whatsapp_user_schema() -> None:
    """Pastikan tabel whatsapp_users tersedia dan terisi dari chat_logs."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS whatsapp_users (
                id SERIAL PRIMARY KEY,
                whatsapp_user_id BIGINT UNIQUE NOT NULL,
                display_name TEXT,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_message_preview TEXT,
                status TEXT NOT NULL DEFAULT '{ACCOUNT_STATUS_ACTIVE}',
                status_reason TEXT,
                status_changed_at TIMESTAMPTZ,
                status_changed_by TEXT,
                metadata JSONB,
                CONSTRAINT whatsapp_users_status_check CHECK (status IN ({STATUS_ENUM_SQL}))
            );
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_whatsapp_users_user
            ON whatsapp_users (whatsapp_user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_whatsapp_users_status
            ON whatsapp_users (status)
            """
        )
    conn.commit()
    _backfill_whatsapp_users()


def _sync_whatsapp_user_profile(
    whatsapp_user_id: Optional[int],
    display_name: Optional[str],
    last_message: Optional[str],
) -> None:
    """Upsert profil WhatsApp berdasarkan chat terbaru."""
    if not whatsapp_user_id:
        return
    _ensure_whatsapp_user_schema()
    clean_name = (display_name or "").strip() or None
    preview = (last_message or "").strip()
    if preview:
        preview = preview[:280]
    else:
        preview = None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO whatsapp_users (
                whatsapp_user_id,
                display_name,
                last_message_preview
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (whatsapp_user_id) DO UPDATE
            SET
                display_name = COALESCE(EXCLUDED.display_name, whatsapp_users.display_name),
                last_seen_at = NOW(),
                last_message_preview = COALESCE(
                    EXCLUDED.last_message_preview,
                    whatsapp_users.last_message_preview
                )
            """,
            (whatsapp_user_id, clean_name, preview),
        )


def _calculate_due_at(category: str) -> datetime:
    base = datetime.now(timezone.utc)
    category = (category or "general").lower()
    if category == "sexual":
        return base + timedelta(hours=12)
    if category == "physical":
        return base + timedelta(hours=24)
    return base + timedelta(hours=48)

def record_psych_report(
    chat_log_id: Optional[int],
    user_id: Optional[int],
    username: Optional[str],
    message: str,
    *,
    severity: str = "general",
    status: str = "open",
    summary: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """Simpan laporan konseling psikologis ke tabel khusus."""
    if not message:
        return None

    payload = Json(metadata) if metadata else None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO psych_reports (
                chat_log_id,
                user_id,
                username,
                message,
                summary,
                severity,
                status,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                chat_log_id,
                user_id,
                username,
                message,
                summary,
                severity,
                status,
                payload,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0]) if row else None

def record_bullying_report(
    chat_log_id: int,
    user_id: Optional[int],
    username: Optional[str],
    description: str,
    *,
    priority: bool = True,
    category: str = "general",
    severity: Optional[str] = None,
    metadata: Optional[dict] = None,
    assigned_to: Optional[str] = None,
) -> Optional[int]:
    """Catat laporan bullying baru dengan status awal 'pending' dan buat notifikasi."""
    if chat_log_id is None:
        raise ValueError("chat_log_id wajib diisi untuk laporan bullying")

    cleaned_description = (description or "").strip()
    if not cleaned_description:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bullying_reports (chat_log_id, user_id, username, description, priority, category, severity, metadata, assigned_to, due_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chat_log_id) DO NOTHING
            RETURNING id
            """,
            (
                chat_log_id,
                user_id,
                username,
                cleaned_description,
                priority,
                category,
                severity,
                Json(metadata) if metadata else None,
                assigned_to,
                _calculate_due_at(category),
            ),
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return None
        report_id = int(row[0])
    conn.commit()
    return report_id


def _resolve_channel(topic: Optional[str]) -> str:
    value = (topic or "").strip().lower()
    if value == "web":
        return "web"
    if value == "twitter":
        return "twitter"
    if value in {"whatsapp", "wa"}:
        return "whatsapp"
    return "telegram"


def save_chat(
    user_id: Optional[int],
    username: Optional[str],
    message: Optional[str],
    role: str,
    topic: Optional[str] = None,
    response_time_ms: Optional[int] = None,
) -> Optional[int]:
    """Simpan chat ke tabel chat_logs dan kembalikan id baris yang dibuat."""
    normalized_topic: Optional[str] = None
    if topic is not None:
        clean_topic = str(topic).strip().lower()
        normalized_topic = clean_topic or None

    use_topic = _chat_logs_has_topic_column()
    use_channel = _chat_logs_has_channel_column()
    channel_value = _resolve_channel(normalized_topic)
    inserted_id: Optional[int] = None

    def _insert_row() -> Optional[int]:
        row_id: Optional[int] = None
        with conn.cursor() as cur:
            if use_topic and use_channel:
                cur.execute(
                    """
                    INSERT INTO chat_logs (
                        user_id,
                        username,
                        text,
                        role,
                        topic,
                        channel,
                        created_at,
                        response_time_ms
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        username,
                        message,
                        role,
                        normalized_topic,
                        channel_value,
                        response_time_ms,
                    ),
                )
            elif use_topic:
                cur.execute(
                    """
                    INSERT INTO chat_logs (user_id, username, text, role, topic, created_at, response_time_ms)
                    VALUES (%s, %s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        username,
                        message,
                        role,
                        normalized_topic,
                        response_time_ms,
                    ),
                )
            elif use_channel:
                cur.execute(
                    """
                    INSERT INTO chat_logs (user_id, username, text, role, channel, created_at, response_time_ms)
                    VALUES (%s, %s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        username,
                        message,
                        role,
                        channel_value,
                        response_time_ms,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO chat_logs (user_id, username, text, role, created_at, response_time_ms)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                    """,
                    (user_id, username, message, role, response_time_ms),
                )
            row = cur.fetchone()
            if row:
                row_id = int(row[0])

            if normalized_topic and row_id and not use_topic:
                topic_supported = _chat_logs_has_topic_column(force_refresh=True)
                if not topic_supported:
                    try:
                        _ensure_chat_logs_schema()
                    except Exception:
                        topic_supported = False
                    else:
                        topic_supported = _chat_logs_has_topic_column(force_refresh=True)
                if topic_supported:
                    cur.execute(
                        "UPDATE chat_logs SET topic = %s WHERE id = %s",
                        (normalized_topic, row_id),
                    )
        return row_id

    try:
        inserted_id = _insert_row()
    except IntegrityError as exc:
        conn.rollback()
        if "chat_logs_pkey" not in str(exc):
            raise
        _reset_chat_logs_sequence()
        inserted_id = _insert_row()
    if role == "user" and user_id is not None:
        if channel_value == "telegram":
            _sync_telegram_user_profile(user_id, username, message)
        elif channel_value == "whatsapp":
            _sync_whatsapp_user_profile(user_id, username, message)

    conn.commit()
    return inserted_id

def get_chat_history(user_id: int, limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Ambil riwayat chat dengan paginasi, mengembalikan list of dictionaries.
    Urutan: Terbaru di atas (DESC).
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT role, text, created_at FROM chat_logs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset),
        )
        return cur.fetchall()


def get_portal_school_by_npsn(npsn: str) -> Optional[Dict[str, Any]]:
    _ensure_guestbook_general_schema()
    clean_npsn = (npsn or "").strip()
    if not clean_npsn:
        return None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, npsn, name, jenjang, alamat, active, logo_url, metadata
            FROM portal_schools
            WHERE npsn = %s
            LIMIT 1
            """,
            (clean_npsn,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def find_general_guest_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    _ensure_guestbook_general_schema()
    normalized = _normalize_phone(phone)
    if not normalized:
        return None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id,
                full_name,
                email,
                phone,
                instansi,
                jabatan,
                is_parent,
                student_class,
                student_name,
                is_verified
            FROM daftar_tamu_general_guests
            WHERE is_deleted = FALSE
              AND regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') = %s
            ORDER BY is_verified DESC, id DESC
            LIMIT 1
            """,
            (normalized,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def create_public_guestbook_transaction(
    *,
    school_id: int,
    purpose: Optional[str],
    notes: Optional[str],
    guests: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not guests:
        raise ValueError("Guests are required")
    _ensure_guestbook_general_schema()
    _ensure_guestbook_hospitality_schema()
    review_token = secrets.token_urlsafe(24)
    transaction_id: Optional[int] = None
    review_row: Optional[Dict[str, Any]] = None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO daftar_tamu_general_transactions (
                    school_id,
                    visit_at,
                    purpose,
                    notes,
                    status,
                    reviewed_by,
                    reviewed_at,
                    reviewer_notes,
                    metadata
                )
                VALUES (%s, NOW(), %s, %s, 'pending', NULL, NULL, NULL, %s)
                RETURNING id
                """,
                (
                    school_id,
                    (purpose or None),
                    (notes or None),
                    Json(metadata) if metadata else None,
                ),
            )
            tx_row = cur.fetchone()
            transaction_id = int(tx_row["id"]) if tx_row else None

            for guest in guests:
                full_name = (guest.get("full_name") or "").strip()
                if not full_name:
                    continue
                phone_raw = (guest.get("phone") or "").strip()
                phone = _normalize_phone(phone_raw) or None
                instansi = (guest.get("instansi") or "").strip() or None
                jabatan = (guest.get("jabatan") or "").strip() or None
                email = (guest.get("email") or "").strip() or None
                student_class = (guest.get("student_class") or "").strip() or None
                student_name = (guest.get("student_name") or "").strip() or None
                is_parent = bool(guest.get("is_parent"))

                if is_parent:
                    instansi = None
                    jabatan = None
                else:
                    student_class = None
                    student_name = None

                if phone:
                    cur.execute(
                        """
                        SELECT id
                        FROM daftar_tamu_general_guests
                        WHERE is_deleted = FALSE
                          AND regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') = %s
                        ORDER BY is_verified DESC, id DESC
                        LIMIT 1
                        """,
                        (phone,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id
                        FROM daftar_tamu_general_guests
                        WHERE lower(full_name) = lower(%s)
                          AND COALESCE(instansi, '') = COALESCE(%s, '')
                          AND COALESCE(jabatan, '') = COALESCE(%s, '')
                          AND COALESCE(email, '') = COALESCE(%s, '')
                          AND is_deleted = FALSE
                        ORDER BY is_verified DESC, id DESC
                        LIMIT 1
                        """,
                        (full_name, instansi or "", jabatan or "", email or ""),
                    )
                existing = cur.fetchone()
                if existing:
                    guest_id = int(existing["id"])
                    cur.execute(
                        """
                        UPDATE daftar_tamu_general_guests
                        SET full_name = %s,
                            email = %s,
                            phone = %s,
                            instansi = %s,
                            jabatan = %s,
                            is_parent = %s,
                            student_class = %s,
                            student_name = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            full_name,
                            email,
                            phone,
                            instansi,
                            jabatan,
                            is_parent,
                            student_class,
                            student_name,
                            guest_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO daftar_tamu_general_guests (
                            full_name,
                            email,
                            phone,
                            instansi,
                            jabatan,
                            is_parent,
                            student_class,
                            student_name,
                            created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                        RETURNING id
                        """,
                        (full_name, email, phone, instansi, jabatan, is_parent, student_class, student_name),
                    )
                    guest_row = cur.fetchone()
                    guest_id = int(guest_row["id"]) if guest_row else None

                cur.execute(
                    """
                    INSERT INTO daftar_tamu_general_transaction_guests (
                        transaction_id,
                        general_guest_id,
                        full_name,
                        phone,
                        instansi,
                        jabatan,
                        email,
                        student_class,
                        student_name
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (transaction_id, guest_id, full_name, phone, instansi, jabatan, email, student_class, student_name),
                )

            if transaction_id:
                cur.execute(
                    """
                    INSERT INTO hospitality_guestbook_reviews (
                        transaction_id,
                        school_id,
                        review_token,
                        status
                    )
                    VALUES (%s, %s, %s, 'pending')
                    ON CONFLICT (transaction_id) DO UPDATE
                    SET school_id = EXCLUDED.school_id,
                        review_token = COALESCE(hospitality_guestbook_reviews.review_token, EXCLUDED.review_token),
                        updated_at = NOW()
                    RETURNING id, transaction_id, school_id, review_token, status, rating, comment, completed_at, created_at, updated_at
                    """,
                    (transaction_id, school_id, review_token),
                )
                review_row = cur.fetchone()

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    if not transaction_id:
        raise ValueError("Failed to create transaction")
    return {
        "transaction_id": transaction_id,
        "review_id": int(review_row["id"]) if review_row and review_row.get("id") is not None else None,
        "review_token": review_row["review_token"] if review_row and review_row.get("review_token") else review_token,
    }


def _fetch_public_guestbook_review_detail(where_sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    _ensure_guestbook_hospitality_schema()
    query = f"""
        SELECT
            r.id AS review_id,
            r.transaction_id,
            r.school_id,
            r.review_token,
            r.status AS review_status,
            r.rating,
            r.comment,
            r.completed_at,
            r.created_at,
            r.updated_at,
            t.visit_at,
            t.status AS transaction_status,
            t.purpose,
            t.notes,
            t.reviewed_by,
            t.reviewed_at,
            t.reviewer_notes,
            s.name AS school_name,
            s.npsn,
            s.jenjang,
            (
                SELECT STRING_AGG(g.full_name, ', ' ORDER BY g.full_name)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_names,
            (
                SELECT COUNT(*)
                FROM daftar_tamu_general_transaction_guests g
                WHERE g.transaction_id = t.id
            ) AS guest_count
        FROM hospitality_guestbook_reviews r
        JOIN daftar_tamu_general_transactions t ON t.id = r.transaction_id
        JOIN portal_schools s ON s.id = r.school_id
        WHERE {where_sql}
        LIMIT 1
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if not row:
            return None
        detail = dict(row)
        cur.execute(
            """
            SELECT
                q.id,
                q.question_text,
                q.sort_order,
                q.active,
                a.rating
            FROM hospitality_guestbook_extra_questions q
            LEFT JOIN hospitality_guestbook_extra_answers a
                ON a.question_id = q.id
               AND a.review_id = %s
            WHERE q.active = TRUE
            ORDER BY q.sort_order ASC, q.id ASC
            """,
            (detail.get("review_id"),),
        )
        questions = [dict(item) for item in (cur.fetchall() or [])]
    detail["extra_questions"] = questions
    detail["extra_ratings"] = {
        int(item["id"]): int(item["rating"])
        for item in questions
        if item.get("rating") is not None
    }
    return detail


def list_public_guestbook_extra_questions(*, active_only: bool = True) -> List[Dict[str, Any]]:
    _ensure_guestbook_hospitality_schema()
    where_sql = "WHERE active = TRUE" if active_only else ""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT id, question_text, sort_order, active
            FROM hospitality_guestbook_extra_questions
            {where_sql}
            ORDER BY sort_order ASC, id ASC
            """
        )
        rows = cur.fetchall() or []
    return [dict(row) for row in rows]


def get_public_guestbook_review_by_token(review_token: str) -> Optional[Dict[str, Any]]:
    clean_token = (review_token or "").strip()
    if not clean_token:
        return None
    return _fetch_public_guestbook_review_detail("r.review_token = %s", (clean_token,))


def get_public_guestbook_review_by_transaction(transaction_id: int) -> Optional[Dict[str, Any]]:
    if not transaction_id:
        return None
    return _fetch_public_guestbook_review_detail("r.transaction_id = %s", (transaction_id,))


def submit_public_guestbook_review(
    *,
    review_token: str,
    rating: int,
    comment: Optional[str] = None,
    extra_ratings: Optional[Dict[Any, Any]] = None,
) -> Dict[str, Any]:
    _ensure_guestbook_hospitality_schema()
    clean_token = (review_token or "").strip()
    if not clean_token:
        raise ValueError("Review token wajib diisi")
    try:
        clean_rating = int(rating)
    except (TypeError, ValueError):
        raise ValueError("Rating harus berupa angka 1 sampai 5")
    if clean_rating < 1 or clean_rating > 5:
        raise ValueError("Rating harus antara 1 sampai 5")
    clean_comment = (comment or "").strip() or None
    raw_extra = extra_ratings or {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id
                FROM hospitality_guestbook_extra_questions
                WHERE active = TRUE
                ORDER BY sort_order ASC, id ASC
                """
            )
            active_questions = [int(item["id"]) for item in (cur.fetchall() or [])]
            normalized_extra: Dict[int, int] = {}
            for qid in active_questions:
                value = raw_extra.get(qid)
                if value is None:
                    value = raw_extra.get(str(qid))
                try:
                    rating_value = int(value)
                except (TypeError, ValueError):
                    rating_value = 0
                if rating_value < 1 or rating_value > 5:
                    raise ValueError("Semua aspek tambahan wajib diisi bintang 1 sampai 5.")
                normalized_extra[qid] = rating_value

            cur.execute(
                """
                SELECT id, transaction_id, school_id, review_token, status, rating, comment, completed_at, created_at, updated_at
                FROM hospitality_guestbook_reviews
                WHERE review_token = %s
                LIMIT 1
                """,
                (clean_token,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Review tidak ditemukan")
            if (row.get("status") or "").lower() == "completed":
                return dict(row)

            cur.execute(
                """
                UPDATE hospitality_guestbook_reviews
                SET status = 'completed',
                    rating = %s,
                    comment = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE review_token = %s
                RETURNING id, transaction_id, school_id, review_token, status, rating, comment, completed_at, created_at, updated_at
                """,
                (clean_rating, clean_comment, clean_token),
            )
            updated = cur.fetchone()
            if updated and normalized_extra:
                review_id = int(updated["id"])
                for qid, extra_rating in normalized_extra.items():
                    cur.execute(
                        """
                        INSERT INTO hospitality_guestbook_extra_answers (
                            review_id, question_id, rating, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, NOW(), NOW())
                        ON CONFLICT (review_id, question_id)
                        DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()
                        """,
                        (review_id, qid, extra_rating),
                    )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    if not updated:
        return dict(row)
    return dict(updated)

def get_or_create_web_user(
    email: str,
    full_name: Optional[str],
    photo_url: Optional[str] = None,
    *,
    access_tier: str = "full",
    auth_provider: Optional[str] = None,
    quota_limit: Optional[int] = None,
    limited_reason: Optional[str] = None,
) -> dict:
    """Ambil user berdasarkan email, atau buat jika belum ada, lalu perbarui informasi login."""
    _ensure_user_schema()
    now_utc = datetime.now(timezone.utc)
    normalized_tier = (access_tier or "full").strip().lower()
    if normalized_tier not in {"full", "limited"}:
        normalized_tier = "full"

    is_limited = normalized_tier == "limited"
    desired_quota_limit = (
        quota_limit
        if quota_limit is not None
        else (DEFAULT_LIMITED_QUOTA if is_limited else None)
    )
    effective_reason = (
        limited_reason
        if (limited_reason and is_limited)
        else (DEFAULT_LIMITED_REASON if is_limited else None)
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id, email, full_name, photo_url, last_login,
                auth_provider, access_tier, quota_limit,
                quota_remaining, quota_reset_at, limited_reason,
                status, status_reason, status_changed_at,
                status_changed_by, metadata
            FROM web_users
            WHERE email = %s
            """,
            (email,),
        )
        existing_user = cur.fetchone()
        if existing_user:
            update_clauses = [
                "full_name = COALESCE(%s, full_name)",
                "photo_url = COALESCE(%s, photo_url)",
                "last_login = %s",
            ]
            params: List[Any] = [full_name, photo_url, now_utc]

            if auth_provider:
                update_clauses.append("auth_provider = COALESCE(%s, auth_provider)")
                params.append(auth_provider)

            if existing_user.get("access_tier") != normalized_tier:
                update_clauses.append("access_tier = %s")
                params.append(normalized_tier)

            if is_limited:
                limit_value = desired_quota_limit or DEFAULT_LIMITED_QUOTA
                if existing_user.get("quota_limit") != limit_value:
                    update_clauses.append("quota_limit = %s")
                    params.append(limit_value)
                if (
                    existing_user.get("quota_remaining") is None
                    or existing_user.get("access_tier") != "limited"
                ):
                    update_clauses.append("quota_remaining = %s")
                    params.append(limit_value)
                    update_clauses.append("quota_reset_at = NULL")
                if effective_reason:
                    update_clauses.append("limited_reason = %s")
                    params.append(effective_reason)
            else:
                update_clauses.extend(
                    [
                        "quota_limit = NULL",
                        "quota_remaining = NULL",
                        "quota_reset_at = NULL",
                        "limited_reason = NULL",
                    ]
                )

            query = f"""
                UPDATE web_users
                SET {', '.join(update_clauses)}
                WHERE email = %s
                RETURNING
                    id, email, full_name, photo_url, last_login,
                    auth_provider, access_tier, quota_limit,
                    quota_remaining, quota_reset_at, limited_reason,
                    status, status_reason, status_changed_at,
                    status_changed_by, metadata
            """
            params.append(email)
            cur.execute(query, params)
            updated_user = cur.fetchone()
            conn.commit()
            return updated_user or existing_user

        cur.execute(
            """
            INSERT INTO web_users (
                email,
                full_name,
                photo_url,
                last_login,
                auth_provider,
                access_tier,
                quota_limit,
                quota_remaining,
                quota_reset_at,
                limited_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING
                id, email, full_name, photo_url, last_login,
                auth_provider, access_tier, quota_limit,
                quota_remaining, quota_reset_at, limited_reason,
                status, status_reason, status_changed_at,
                status_changed_by, metadata
            """,
            (
                email,
                full_name,
                photo_url,
                now_utc,
                auth_provider,
                normalized_tier,
                desired_quota_limit,
                desired_quota_limit if is_limited else None,
                None,
                effective_reason,
            ),
        )
        new_user = cur.fetchone()
    conn.commit()
    return new_user

def _maybe_reset_quota(
    cur,
    user_id: int,
    row: Dict[str, Any],
    now: datetime,
) -> Tuple[Dict[str, Any], bool]:
    """Reset kuota user terbatas jika cooldown sudah lewat."""
    updated = False
    if (row.get("access_tier") or "full") != "limited":
        return row, updated

    limit_value = row.get("quota_limit") or DEFAULT_LIMITED_QUOTA
    if row.get("quota_limit") != limit_value:
        cur.execute(
            "UPDATE web_users SET quota_limit = %s WHERE id = %s",
            (limit_value, user_id),
        )
        row["quota_limit"] = limit_value
        updated = True

    quota_remaining = row.get("quota_remaining")
    reset_at = row.get("quota_reset_at")

    if quota_remaining is None:
        cur.execute(
            """
            UPDATE web_users
            SET quota_remaining = %s,
                quota_reset_at = NULL
            WHERE id = %s
            """,
            (limit_value, user_id),
        )
        row["quota_remaining"] = limit_value
        row["quota_reset_at"] = None
        updated = True
        return row, updated

    if reset_at and reset_at <= now:
        cur.execute(
            """
            UPDATE web_users
            SET quota_remaining = %s,
                quota_reset_at = NULL
            WHERE id = %s
            """,
            (limit_value, user_id),
        )
        row["quota_remaining"] = limit_value
        row["quota_reset_at"] = None
        updated = True

    return row, updated


def get_web_user_status(user_id: int) -> Dict[str, Any]:
    """Ambil status akun web terbaru."""
    _ensure_user_schema()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id,
                email,
                full_name,
                status,
                status_reason,
                status_changed_at,
                status_changed_by
            FROM web_users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return {
            "id": user_id,
            "status": ACCOUNT_STATUS_ACTIVE,
            "status_reason": None,
            "status_changed_at": None,
            "status_changed_by": None,
        }
    return dict(row)


def get_telegram_user_status(user_id: int) -> Dict[str, Any]:
    """Ambil status akun Telegram berdasarkan telegram_user_id."""
    _ensure_telegram_user_schema()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                telegram_user_id,
                username,
                status,
                status_reason,
                status_changed_at,
                status_changed_by
            FROM telegram_users
            WHERE telegram_user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return {
            "telegram_user_id": user_id,
            "status": ACCOUNT_STATUS_ACTIVE,
            "status_reason": None,
            "status_changed_at": None,
            "status_changed_by": None,
        }
    return dict(row)


def get_whatsapp_user_status(user_id: int) -> Dict[str, Any]:
    """Ambil status akun WhatsApp berdasarkan whatsapp_user_id."""
    _ensure_whatsapp_user_schema()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                whatsapp_user_id,
                display_name,
                status,
                status_reason,
                status_changed_at,
                status_changed_by
            FROM whatsapp_users
            WHERE whatsapp_user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return {
            "whatsapp_user_id": user_id,
            "status": ACCOUNT_STATUS_ACTIVE,
            "status_reason": None,
            "status_changed_at": None,
            "status_changed_by": None,
        }
    return dict(row)


def get_chat_quota_status(user_id: int) -> Dict[str, Any]:
    """Ambil status kuota chat user web, sekaligus reset jika cooldown selesai."""
    _ensure_user_schema()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id, access_tier, quota_limit,
                quota_remaining, quota_reset_at, limited_reason
            FROM web_users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {
                "access_tier": "full",
                "quota_limit": None,
                "quota_remaining": None,
                "quota_reset_at": None,
                "limited_reason": None,
            }

        now = datetime.now(timezone.utc)
        row, updated = _maybe_reset_quota(cur, user_id, row, now)
        if updated:
            conn.commit()
        return {
            "access_tier": row.get("access_tier") or "full",
            "quota_limit": row.get("quota_limit"),
            "quota_remaining": row.get("quota_remaining"),
            "quota_reset_at": row.get("quota_reset_at"),
            "limited_reason": row.get("limited_reason"),
        }


def consume_chat_quota(user_id: int) -> Dict[str, Any]:
    """
    Kurangi kuota chat user terbatas sebanyak 1.
    Mengembalikan detail status kuota serta flag apakah request boleh dilanjut.
    """
    _ensure_user_schema()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id, access_tier, quota_limit,
                quota_remaining, quota_reset_at, limited_reason
            FROM web_users
            WHERE id = %s
            FOR UPDATE
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.commit()
            return {
                "allowed": False,
                "access_tier": None,
                "quota_limit": None,
                "quota_remaining": None,
                "quota_reset_at": None,
                "limited_reason": None,
                "error": "user_not_found",
            }

        now = datetime.now(timezone.utc)
        row, updated = _maybe_reset_quota(cur, user_id, row, now)
        access_tier = row.get("access_tier") or "full"

        if access_tier != "limited":
            conn.commit()
            return {
                "allowed": True,
                "access_tier": access_tier,
                "quota_limit": row.get("quota_limit"),
                "quota_remaining": row.get("quota_remaining"),
                "quota_reset_at": row.get("quota_reset_at"),
                "limited_reason": row.get("limited_reason"),
            }

        limit_value = row.get("quota_limit") or DEFAULT_LIMITED_QUOTA
        quota_remaining = row.get("quota_remaining")
        reset_at = row.get("quota_reset_at")

        if quota_remaining is None:
            quota_remaining = limit_value
            cur.execute(
                """
                UPDATE web_users
                SET quota_remaining = %s,
                    quota_reset_at = NULL
                WHERE id = %s
                """,
                (quota_remaining, user_id),
            )
            updated = True

        if quota_remaining <= 0:
            if not reset_at:
                reset_at = now + timedelta(hours=LIMIT_COOLDOWN_HOURS)
                cur.execute(
                    "UPDATE web_users SET quota_reset_at = %s WHERE id = %s",
                    (reset_at, user_id),
                )
                updated = True
            conn.commit()
            return {
                "allowed": False,
                "access_tier": access_tier,
                "quota_limit": limit_value,
                "quota_remaining": 0,
                "quota_reset_at": reset_at,
                "limited_reason": row.get("limited_reason") or DEFAULT_LIMITED_REASON,
            }

        new_remaining = max(0, quota_remaining - 1)
        new_reset_at = reset_at
        # Start cooldown timer when first chat is used (quota decreases from full)
        # This ensures quota refills after 24 hours from first usage, not from depletion
        if new_reset_at is None:
            new_reset_at = now + timedelta(hours=LIMIT_COOLDOWN_HOURS)

        cur.execute(
            """
            UPDATE web_users
            SET quota_remaining = %s,
                quota_reset_at = %s
            WHERE id = %s
            """,
            (new_remaining, new_reset_at, user_id),
        )
        conn.commit()
        return {
            "allowed": True,
            "access_tier": access_tier,
            "quota_limit": limit_value,
            "quota_remaining": new_remaining,
            "quota_reset_at": new_reset_at,
            "limited_reason": row.get("limited_reason") or DEFAULT_LIMITED_REASON,
        }

def _ensure_corruption_schema() -> None:
    """Pastikan tabel untuk laporan korupsi (corruption_reports) tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS corruption_reports (
                id SERIAL PRIMARY KEY,
                ticket_id TEXT UNIQUE NOT NULL,
                user_id BIGINT,
                status TEXT NOT NULL DEFAULT 'open',
                involved TEXT,
                location TEXT,
                time TEXT,
                chronology TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK (status IN ('open', 'in_progress', 'resolved', 'archived'))
            );
            """
        )
    conn.commit()

def record_corruption_report(data: Dict[str, Any]) -> Optional[int]:
    """Simpan laporan korupsi ke tabel khusus."""
    if not data or not data.get("ticket_id"):
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO corruption_reports (
                ticket_id, user_id, status, involved, location, time, chronology
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data.get("ticket_id"),
                data.get("user_id"),
                data.get("status", "open"),
                data.get("involved"),
                data.get("location"),
                data.get("time"),
                data.get("chronology"),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0]) if row else None

def get_corruption_report(ticket_id: str) -> Optional[Dict[str, Any]]:
    """Ambil detail laporan korupsi berdasarkan tiket."""
    if not ticket_id:
        return None

    normalized_ticket = ticket_id.strip().upper()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                ticket_id,
                status,
                involved,
                location,
                time,
                chronology,
                created_at,
                updated_at
            FROM corruption_reports
            WHERE ticket_id = %s
            """,
            (normalized_ticket,),
        )
        report = cur.fetchone()

    return report

def _ensure_twitter_log_schema() -> None:
    """Pastikan tabel penyimpanan log worker Twitter tersedia."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS twitter_worker_logs (
                id SERIAL PRIMARY KEY,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                context JSONB,
                tweet_id BIGINT,
                twitter_user_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_twitter_worker_logs_created
            ON twitter_worker_logs (created_at DESC);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_twitter_worker_logs_level
            ON twitter_worker_logs (level);
            """
        )
    conn.commit()

def record_twitter_log(
    level: str,
    message: str,
    *,
    tweet_id: Optional[int] = None,
    twitter_user_id: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Simpan log worker Twitter ke database untuk dipantau via dashboard."""
    if not message:
        return
    clean_level = (level or "INFO").strip().upper()
    clean_message = message.strip()
    if not clean_message:
        return
    if len(clean_message) > 4000:
        clean_message = clean_message[:4000]

    context_payload: Optional[Dict[str, Any]] = None
    if context:
        context_payload = {}
        for key, value in context.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool, dict, list)):
                context_payload[key] = value
            else:
                context_payload[key] = str(value)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO twitter_worker_logs (level, message, context, tweet_id, twitter_user_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                clean_level,
                clean_message,
                Json(context_payload) if context_payload else None,
                tweet_id,
                twitter_user_id,
            ),
        )
        if MAX_TWITTER_LOG_ROWS > 0:
            cur.execute(
                """
                DELETE FROM twitter_worker_logs
                WHERE id NOT IN (
                    SELECT id
                    FROM twitter_worker_logs
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                )
                """,
                (MAX_TWITTER_LOG_ROWS,),
                )
    conn.commit()

def ensure_db_schema() -> None:
    """Create or update core database tables when explicitly requested."""
    _ensure_chat_logs_schema()
    _ensure_bullying_schema()
    _ensure_psych_schema()
    _ensure_user_schema()
    _ensure_guestbook_general_schema()
    _ensure_guestbook_hospitality_schema()
    _ensure_telegram_user_schema()
    _ensure_whatsapp_user_schema()
    _ensure_corruption_schema()
    _ensure_twitter_log_schema()


if os.getenv("ASKA_DB_AUTO_INIT", "").strip().lower() in {"1", "true", "yes"}:
    ensure_db_schema()
