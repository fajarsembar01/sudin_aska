"""Routes for the Adiwiyata feature."""

from __future__ import annotations

import json
import os
import re
import uuid

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from dashboard.daftar_tamu.queries import (
    USER_APP_NOTIFICATION_CATEGORIES,
    fetch_user_notification_summary,
)
from dashboard.portal.routes import (
    UPLOAD_FOLDER,
    _fetch_user_school,
    _normalize_metadata,
)

adiwiyata_bp = Blueprint(
    "adiwiyata",
    __name__,
    template_folder="templates",
    url_prefix="/adiwiyata",
)

# Preserve existing public URLs under /portal/api and /portal/public while the
# feature code lives in dashboard/adiwiyata.
adiwiyata_api_bp = Blueprint(
    "adiwiyata_api",
    __name__,
    url_prefix="/portal",
)

# ===== Adiwiyata Posts Operations =====

_ADIWIYATA_SHARE_PROMPT_SESSION_KEY = "adiwiyata_share_prompt"


def _adiwiyata_public_share_base_url() -> str:
    value = os.getenv("ADIWIYATA_PUBLIC_URL", "").strip()
    return (value or "https://sudindikju2.com/adiwiyata").rstrip("/")


def _adiwiyata_public_share_url(post_id: int | None = None) -> str:
    base_url = _adiwiyata_public_share_base_url()
    if post_id:
        return f"{base_url}#post-{post_id}"
    return base_url


def _adiwiyata_category_title(category: str) -> str:
    category_titles = {
        "pengelolaan-sampah": "Pengelolaan Sampah",
        "konservasi-energi": "Konservasi Energi",
        "konservasi-air": "Konservasi Air",
        "kebersihan-sanitasi-drainase": "Kebersihan, Sanitasi, Drainase",
        "kompos": "Kompos",
        "tanaman": "Tanaman",
    }
    return category_titles.get(category, category.replace("-", " ").title())


def _queue_adiwiyata_share_prompt(post: dict | None, school: dict, category: str, title: str, post_kind: str) -> None:
    if not post:
        return

    post_id = post.get("id") if hasattr(post, "get") else None
    if not post_id:
        return

    session[_ADIWIYATA_SHARE_PROMPT_SESSION_KEY] = {
        "post_id": int(post_id),
        "school_id": int(school["id"]),
        "school_name": school.get("name") or "Sekolah",
        "category": category,
        "category_title": title,
        "post_kind": post_kind,
        "share_url": _adiwiyata_public_share_url(int(post_id)),
    }


_ADIWIYATA_THUMBNAIL_COLUMN: bool | None = None


def _adiwiyata_has_thumbnail_column() -> bool:
    global _ADIWIYATA_THUMBNAIL_COLUMN
    if _ADIWIYATA_THUMBNAIL_COLUMN is not None:
        return _ADIWIYATA_THUMBNAIL_COLUMN
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'portal_adiwiyata_posts'
                  AND column_name = 'thumbnail_path'
            ) AS exists
            """
        )
        row = cur.fetchone()
    _ADIWIYATA_THUMBNAIL_COLUMN = bool((row or {}).get("exists"))
    return _ADIWIYATA_THUMBNAIL_COLUMN


def create_adiwiyata_post(school_id: int, category: str, media_path: str, media_type: str, description: str, user_id: int, thumbnail_path: str | None = None) -> dict | None:
    has_thumbnail_column = _adiwiyata_has_thumbnail_column()
    with get_cursor(commit=True) as cur:
        if has_thumbnail_column:
            cur.execute(
                """
                INSERT INTO portal_adiwiyata_posts 
                (school_id, category, media_path, media_type, description, created_by, thumbnail_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (school_id, category, media_path, media_type, description, user_id, thumbnail_path)
            )
        else:
            cur.execute(
                """
                INSERT INTO portal_adiwiyata_posts 
                (school_id, category, media_path, media_type, description, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (school_id, category, media_path, media_type, description, user_id)
            )
        return cur.fetchone()

def list_adiwiyata_posts(school_id: int, category: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.*, u.full_name as author_name 
            FROM portal_adiwiyata_posts p
            LEFT JOIN dashboard_users u ON p.created_by = u.id
            WHERE p.school_id = %s AND p.category = %s
            ORDER BY p.created_at DESC
            """,
            (school_id, category)
        )
        raw_rows = cur.fetchall()
        import json
        from flask import url_for
        rows = []
        for raw in raw_rows:
            row = dict(raw)
            row["media_urls"] = None
            row["media_paths"] = None
            row["thumbnail_path"] = row.get("thumbnail_path")
            if row.get("media_type") == "image":
                val = row.get("media_path") or ""
                is_json = False
                if val.strip().startswith("[") and val.strip().endswith("]"):
                    try:
                        paths = json.loads(val)
                        if isinstance(paths, list):
                            row["media_urls"] = [url_for("portal.uploaded_file", filename=p) for p in paths]
                            row["media_paths"] = paths
                            if paths:
                                row["media_path"] = paths[0]
                            is_json = True
                    except Exception:
                        pass
                if not is_json:
                    if val:
                        row["media_urls"] = [url_for("portal.uploaded_file", filename=val)]
                    else:
                        row["media_urls"] = []
            rows.append(row)
        return rows

def update_adiwiyata_post(post_id: int, description: str) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE portal_adiwiyata_posts
            SET description = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (description, post_id)
        )
        return cur.rowcount > 0

def get_adiwiyata_post(post_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM portal_adiwiyata_posts WHERE id = %s", (post_id,))
        return cur.fetchone()

def delete_adiwiyata_post(post_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM portal_adiwiyata_posts WHERE id = %s", (post_id,))
        return cur.rowcount > 0


def _build_school_logo_url(logo_url: str | None, external: bool = False) -> str | None:
    value = (logo_url or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value

    normalized = value.replace("\\", "/")
    marker = "/portal/uploads/"
    if marker in normalized:
        filename = normalized.split(marker, 1)[1]
        return url_for("portal.uploaded_file", filename=filename, _external=external)

    normalized = normalized.lstrip("/")
    if normalized.startswith("portal/uploads/"):
        normalized = normalized[len("portal/uploads/") :]
    elif normalized.startswith("uploads/"):
        normalized = normalized[len("uploads/") :]

    rel = PurePosixPath(normalized)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    return url_for("portal.uploaded_file", filename=rel.as_posix(), _external=external)


def _normalize_external_url(value: str | None, default_scheme: str = "https") -> str | None:
    clean = (value or "").strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://", "mailto:", "tel:")):
        return clean
    return f"{default_scheme}://{clean.lstrip('/')}"


def _build_social_profile_url(kind: str, value: str | None) -> str | None:
    clean = (value or "").strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://")):
        return clean

    username = clean.lstrip("@").strip("/")
    if not username:
        return None

    if kind == "instagram":
        return f"https://instagram.com/{username}"
    if kind == "tiktok":
        return f"https://www.tiktok.com/@{username}"
    if kind == "telegram":
        return f"https://t.me/{username}"
    return _normalize_external_url(clean)


def _fetch_public_school_profile(school_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                s.id,
                s.npsn,
                s.name,
                s.jenjang,
                s.alamat,
                s.status,
                s.logo_url,
                s.metadata,
                l.name AS kelurahan_name,
                k.name AS kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE s.id = %s
            """,
            (school_id,),
        )
        row = cur.fetchone()
    if not row:
        return None

    school = dict(row)
    meta = _normalize_metadata(school.get("metadata"))
    school["metadata"] = meta
    school["logo_url"] = _build_school_logo_url(school.get("logo_url"), external=False)

    stats = [
        {"label": "Siswa", "value": meta.get("student_count")},
        {"label": "Inklusi", "value": meta.get("inclusion_student_count")},
        {"label": "Guru", "value": meta.get("teacher_count")},
        {"label": "Tendik", "value": meta.get("staff_count")},
        {"label": "Rombel", "value": meta.get("rombel_count")},
    ]
    school["public_stats"] = [
        item for item in stats
        if item["value"] is not None and str(item["value"]).strip() != ""
    ]

    contacts = []
    if meta.get("school_phone"):
        contacts.append({
            "label": "Telepon",
            "value": str(meta.get("school_phone")).strip(),
            "href": f"tel:{str(meta.get('school_phone')).strip()}",
            "icon": "bi-telephone",
        })
    if meta.get("cs_email"):
        contacts.append({
            "label": "Email",
            "value": str(meta.get("cs_email")).strip(),
            "href": f"mailto:{str(meta.get('cs_email')).strip()}",
            "icon": "bi-envelope",
        })
    school["public_contacts"] = contacts

    links = []
    link_specs = [
        ("website", "Website", "bi-globe2", _normalize_external_url(meta.get("website"))),
        ("gmaps_url", "Maps", "bi-geo-alt", _normalize_external_url(meta.get("gmaps_url"))),
        ("instagram", "Instagram", "bi-instagram", _build_social_profile_url("instagram", meta.get("instagram"))),
        ("tiktok", "TikTok", "bi-tiktok", _build_social_profile_url("tiktok", meta.get("tiktok"))),
        ("youtube", "YouTube", "bi-youtube", _build_social_profile_url("youtube", meta.get("youtube"))),
        ("telegram", "Telegram", "bi-telegram", _build_social_profile_url("telegram", meta.get("telegram"))),
        ("wa_channel", "WA Channel", "bi-whatsapp", _normalize_external_url(meta.get("wa_channel"))),
    ]
    for key, label, icon, href in link_specs:
        raw_value = (meta.get(key) or "").strip() if isinstance(meta.get(key), str) else meta.get(key)
        if raw_value and href:
            links.append({"label": label, "href": href, "icon": icon})
    school["public_links"] = links

    location_parts = [
        school.get("kelurahan_name"),
        school.get("kecamatan_name"),
    ]
    school["public_location"] = ", ".join(str(part) for part in location_parts if part)
    return school


def list_all_adiwiyata_posts_public(limit: int = 20, offset: int = 0) -> list[dict]:
    """Ambil semua postingan adiwiyata dari semua sekolah, diurutkan terbaru."""
    thumbnail_select = "p.thumbnail_path" if _adiwiyata_has_thumbnail_column() else "NULL::text AS thumbnail_path"
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT 
                p.id,
                p.school_id,
                p.category,
                p.media_path,
                p.media_type,
                p.description,
                p.created_at,
                {thumbnail_select},
                s.name AS school_name,
                s.npsn AS school_npsn,
                s.logo_url AS school_logo_url
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )
        raw_rows = cur.fetchall()
    
    import json
    from flask import url_for, request as flask_request
    base_url = ""
    rows = []
    for raw in raw_rows:
        row = dict(raw)
        row["media_urls"] = None
        row["media_paths"] = None
        if row.get("media_type") == "image":
            val = row.get("media_path") or ""
            is_json = False
            if val.strip().startswith("[") and val.strip().endswith("]"):
                try:
                    paths = json.loads(val)
                    if isinstance(paths, list):
                        row["media_urls"] = [url_for("portal.uploaded_file", filename=p, _external=True) for p in paths]
                        row["media_paths"] = paths
                        if paths:
                            row["media_path"] = paths[0]
                        is_json = True
                except Exception:
                    pass
            if not is_json and val:
                row["media_urls"] = [url_for("portal.uploaded_file", filename=val, _external=True)]
        # Serialize created_at
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        row["school_logo_url"] = _build_school_logo_url(row.get("school_logo_url"), external=True)
        rows.append(row)
    return rows


def count_all_adiwiyata_posts() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM portal_adiwiyata_posts")
        row = cur.fetchone()
        return int((row or {}).get("count") or 0)


def list_random_adiwiyata_photos(limit: int = 12) -> list[dict]:
    """Ambil foto acak (image only) dari semua sekolah untuk hero gallery."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                p.id,
                p.school_id,
                p.category,
                p.media_path,
                p.media_type,
                p.description,
                p.created_at,
                s.name AS school_name,
                s.logo_url AS school_logo_url
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            WHERE p.media_type = 'image'
            ORDER BY RANDOM()
            LIMIT %s
            """,
            (limit,)
        )
        raw_rows = cur.fetchall()

    import json
    from flask import url_for
    rows = []
    for raw in raw_rows:
        row = dict(raw)
        val = row.get("media_path") or ""
        urls = []
        if val.strip().startswith("[") and val.strip().endswith("]"):
            try:
                paths = json.loads(val)
                if isinstance(paths, list) and paths:
                    urls = [
                        url_for("portal.uploaded_file", filename=path, _external=True)
                        for path in paths
                        if path
                    ]
            except Exception:
                pass
        if not urls and val:
            urls = [url_for("portal.uploaded_file", filename=val, _external=True)]
        if urls:
            created_at = row.get("created_at")
            rows.append({
                "id": row["id"],
                "url": urls[0],
                "media_urls": urls,
                "school_id": row.get("school_id"),
                "school_name": row.get("school_name", ""),
                "school_logo_url": _build_school_logo_url(row.get("school_logo_url"), external=True),
                "category": row.get("category", ""),
                "description": row.get("description") or "",
                "created_at": created_at.isoformat() if created_at else None,
            })
    return rows


def list_adiwiyata_photos_sorted(limit: int = 6, sort: str = "newest") -> list[dict]:
    """Ambil foto (image only) untuk sidebar, diurut berdasarkan terbaru atau jumlah like."""
    order = "p.created_at DESC"
    if sort == "top":
        order = "COALESCE(lk.likes, 0) DESC, p.created_at DESC"

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                p.id,
                p.school_id,
                p.category,
                p.media_path,
                p.media_type,
                p.description,
                p.created_at,
                s.name AS school_name,
                s.logo_url AS school_logo_url,
                COALESCE(lk.likes, 0) AS likes
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS likes
                FROM adiwiyata_post_likes WHERE action = 'like' GROUP BY post_id
            ) lk ON lk.post_id = p.id
            WHERE p.media_type = 'image'
            ORDER BY {order}
            LIMIT %s
            """,
            (limit,)
        )
        raw_rows = cur.fetchall()

    import json
    from flask import url_for
    rows = []
    for raw in raw_rows:
        row = dict(raw)
        val = row.get("media_path") or ""
        urls = []
        if val.strip().startswith("[") and val.strip().endswith("]"):
            try:
                paths = json.loads(val)
                if isinstance(paths, list) and paths:
                    urls = [
                        url_for("portal.uploaded_file", filename=path, _external=True)
                        for path in paths
                        if path
                    ]
            except Exception:
                pass
        if not urls and val:
            urls = [url_for("portal.uploaded_file", filename=val, _external=True)]
        if urls:
            created_at = row.get("created_at")
            rows.append({
                "id": row["id"],
                "url": urls[0],
                "media_urls": urls,
                "school_id": row.get("school_id"),
                "school_name": row.get("school_name", ""),
                "school_logo_url": _build_school_logo_url(row.get("school_logo_url"), external=True),
                "category": row.get("category", ""),
                "description": row.get("description") or "",
                "created_at": created_at.isoformat() if created_at else None,
                "likes": int(row.get("likes") or 0),
            })
    return rows


# ===== Admin Adiwiyata Routes =====

def _get_adiwiyata_admin_stats() -> dict:
    """Statistik ringkasan untuk dashboard admin adiwiyata."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM portal_adiwiyata_posts")
        total_posts = int((cur.fetchone() or {}).get("count") or 0)

        cur.execute(
            """
            SELECT COUNT(DISTINCT school_id)
            FROM portal_adiwiyata_posts
            """
        )
        total_schools = int((cur.fetchone() or {}).get("count") or 0)

        cur.execute(
            """
            SELECT COUNT(*) FROM portal_adiwiyata_posts
            WHERE created_at >= NOW() - INTERVAL '30 days'
            """
        )
        posts_30d = int((cur.fetchone() or {}).get("count") or 0)

        cur.execute(
            """
            SELECT COUNT(*) FROM adiwiyata_post_likes WHERE action = 'like'
            """
        )
        total_likes = int((cur.fetchone() or {}).get("count") or 0)

        cur.execute(
            """
            SELECT category, COUNT(*) as cnt
            FROM portal_adiwiyata_posts
            GROUP BY category
            ORDER BY cnt DESC
            """
        )
        category_stats = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT DATE(created_at AT TIME ZONE 'Asia/Jakarta') as day, COUNT(*) as cnt
            FROM portal_adiwiyata_posts
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY day
            ORDER BY day
            """
        )
        daily_activity = []
        for r in cur.fetchall():
            d = dict(r)
            if d.get("day") and hasattr(d["day"], "isoformat"):
                d["day"] = d["day"].isoformat()
            daily_activity.append(d)

        cur.execute(
            """
            SELECT s.id, s.name, s.npsn, COUNT(p.id) as post_count
            FROM portal_schools s
            JOIN portal_adiwiyata_posts p ON p.school_id = s.id
            GROUP BY s.id, s.name, s.npsn
            ORDER BY post_count DESC
            LIMIT 10
            """
        )
        top_schools = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT p.id, p.school_id, p.category, p.media_path, p.media_type,
                   p.description, p.created_at, s.name AS school_name,
                   COALESCE(lk.likes, 0) AS likes
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS likes
                FROM adiwiyata_post_likes WHERE action='like' GROUP BY post_id
            ) lk ON lk.post_id = p.id
            ORDER BY p.created_at DESC
            LIMIT 6
            """
        )
        recent_posts = []
        for raw in cur.fetchall():
            row = dict(raw)
            _enrich_adiwiyata_row(row)
            recent_posts.append(row)

    return {
        "total_posts": total_posts,
        "total_schools": total_schools,
        "posts_30d": posts_30d,
        "total_likes": total_likes,
        "category_stats": category_stats,
        "daily_activity": daily_activity,
        "top_schools": top_schools,
        "recent_posts": recent_posts,
    }


def _enrich_adiwiyata_row(row: dict) -> None:
    """Enrich satu baris post adiwiyata: resolve media_urls dan created_at string."""
    import json as _json
    if row.get("media_type") == "image":
        val = row.get("media_path") or ""
        if val.strip().startswith("[") and val.strip().endswith("]"):
            try:
                paths = _json.loads(val)
                if isinstance(paths, list):
                    row["media_urls"] = [url_for("portal.uploaded_file", filename=p) for p in paths]
                    if paths:
                        row["cover_url"] = url_for("portal.uploaded_file", filename=paths[0])
                    return
            except Exception:
                pass
        if val:
            row["cover_url"] = url_for("portal.uploaded_file", filename=val)
            row["media_urls"] = [row["cover_url"]]
        else:
            row["cover_url"] = None
            row["media_urls"] = []
    else:
        row["cover_url"] = None
        row["media_urls"] = []
    if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
        row["created_at_str"] = row["created_at"].strftime("%d %b %Y")
    else:
        row["created_at_str"] = str(row.get("created_at") or "")


def _list_adiwiyata_posts_admin(
    school_id: int | None = None,
    category: str | None = None,
    media_type: str | None = None,
    search: str | None = None,
    sort: str = "newest",
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """List semua post adiwiyata dengan filter, pagination, dan like count."""
    conditions = ["1=1"]
    params: list = []
    if school_id:
        conditions.append("p.school_id = %s")
        params.append(school_id)
    if category:
        conditions.append("p.category = %s")
        params.append(category)
    if media_type:
        conditions.append("p.media_type = %s")
        params.append(media_type)
    if search:
        conditions.append("(p.description ILIKE %s OR s.name ILIKE %s OR s.npsn ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where = " AND ".join(conditions)
    order = "p.created_at DESC"
    if sort == "oldest":
        order = "p.created_at ASC"
    elif sort == "most_liked":
        order = "COALESCE(lk.likes, 0) DESC, p.created_at DESC"
    elif sort == "least_liked":
        order = "COALESCE(lk.likes, 0) ASC, p.created_at DESC"

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            WHERE {where}
            """,
            params,
        )
        total = int((cur.fetchone() or {}).get("count") or 0)

        offset = (page - 1) * per_page
        cur.execute(
            f"""
            SELECT p.id, p.school_id, p.category, p.media_path, p.media_type,
                   p.description, p.created_at, p.updated_at,
                   s.name AS school_name, s.npsn AS school_npsn,
                   u.full_name AS author_name,
                   COALESCE(lk.likes, 0) AS likes,
                   COALESCE(dk.dislikes, 0) AS dislikes
            FROM portal_adiwiyata_posts p
            LEFT JOIN portal_schools s ON p.school_id = s.id
            LEFT JOIN dashboard_users u ON p.created_by = u.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS likes FROM adiwiyata_post_likes
                WHERE action='like' GROUP BY post_id
            ) lk ON lk.post_id = p.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) AS dislikes FROM adiwiyata_post_likes
                WHERE action='dislike' GROUP BY post_id
            ) dk ON dk.post_id = p.id
            WHERE {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s
            """,
            params + [per_page, offset],
        )
        rows = []
        for raw in cur.fetchall():
            row = dict(raw)
            _enrich_adiwiyata_row(row)
            rows.append(row)
    return rows, total


def _list_schools_with_adiwiyata() -> list[dict]:
    """List sekolah + ringkasan post adiwiyata per kategori."""
    categories = [
        "pengelolaan-sampah", "konservasi-energi", "konservasi-air",
        "kebersihan-sanitasi-drainase", "kompos", "tanaman",
    ]
    cat_case = ", ".join(
        f"SUM(CASE WHEN p.category = '{c}' THEN 1 ELSE 0 END) AS \"{c}\""
        for c in categories
    )
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id, s.name, s.npsn, s.jenjang,
                   COUNT(p.id) AS total_posts,
                   MAX(p.created_at) AS last_post_at,
                   COALESCE(lk.total_likes, 0) AS total_likes,
                   {cat_case}
            FROM portal_schools s
            JOIN portal_adiwiyata_posts p ON p.school_id = s.id
            LEFT JOIN (
                SELECT pp.school_id, COUNT(pl.id) AS total_likes
                FROM portal_adiwiyata_posts pp
                JOIN adiwiyata_post_likes pl ON pl.post_id = pp.id AND pl.action = 'like'
                GROUP BY pp.school_id
            ) lk ON lk.school_id = s.id
            GROUP BY s.id, s.name, s.npsn, s.jenjang, lk.total_likes
            ORDER BY total_posts DESC, s.name
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        lp = row.get("last_post_at")
        row["last_post_str"] = lp.strftime("%d %b %Y") if lp and hasattr(lp, "strftime") else ""
        row["category_counts"] = {c: int(row.get(c) or 0) for c in categories}
    return rows


@adiwiyata_bp.route("/admin/", strict_slashes=False)
@role_required("admin")
def admin_adiwiyata_dashboard() -> Response:
    """Admin Adiwiyata — halaman dashboard ringkasan."""
    stats = _get_adiwiyata_admin_stats()
    category_titles = {
        "pengelolaan-sampah": "Pengelolaan Sampah",
        "konservasi-energi": "Konservasi Energi",
        "konservasi-air": "Konservasi Air",
        "kebersihan-sanitasi-drainase": "Kebersihan & Sanitasi",
        "kompos": "Kompos",
        "tanaman": "Tanaman",
    }
    for row in stats.get("category_stats", []):
        row["title"] = category_titles.get(row.get("category", ""), row.get("category", ""))
    return render_template(
        "adiwiyata/admin/dashboard.html",
        stats=stats,
        category_titles=category_titles,
        active_nav="dashboard",
    )


@adiwiyata_bp.route("/admin/posts")
@role_required("admin")
def admin_adiwiyata_posts() -> Response:
    """Admin Adiwiyata — daftar semua post dengan filter & delete."""
    school_id = request.args.get("school_id", type=int)
    category = request.args.get("category", "").strip() or None
    media_type = request.args.get("media_type", "").strip() or None
    search = request.args.get("q", "").strip() or None
    sort = request.args.get("sort", "newest")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24

    posts, total = _list_adiwiyata_posts_admin(
        school_id=school_id,
        category=category,
        media_type=media_type,
        search=search,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, -(-total // per_page))

    # Sekolah list untuk dropdown filter
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT s.id, s.name FROM portal_schools s
            JOIN portal_adiwiyata_posts p ON p.school_id = s.id
            ORDER BY s.name
            """
        )
        schools_filter = [dict(r) for r in cur.fetchall()]

    category_titles = {
        "pengelolaan-sampah": "Pengelolaan Sampah",
        "konservasi-energi": "Konservasi Energi",
        "konservasi-air": "Konservasi Air",
        "kebersihan-sanitasi-drainase": "Kebersihan & Sanitasi",
        "kompos": "Kompos",
        "tanaman": "Tanaman",
    }
    return render_template(
        "adiwiyata/admin/posts.html",
        posts=posts,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        schools_filter=schools_filter,
        category_titles=category_titles,
        selected_school_id=school_id,
        selected_category=category,
        selected_media_type=media_type,
        search=search or "",
        sort=sort,
        active_nav="posts",
    )


@adiwiyata_bp.route("/admin/schools")
@role_required("admin")
def admin_adiwiyata_schools() -> Response:
    """Admin Adiwiyata — ringkasan per sekolah."""
    search = request.args.get("q", "").strip().lower()
    rows = _list_schools_with_adiwiyata()
    if search:
        rows = [r for r in rows if search in (r.get("name") or "").lower()
                or search in (r.get("npsn") or "").lower()]
    category_titles = {
        "pengelolaan-sampah": "Sampah",
        "konservasi-energi": "Energi",
        "konservasi-air": "Air",
        "kebersihan-sanitasi-drainase": "Sanitasi",
        "kompos": "Kompos",
        "tanaman": "Tanaman",
    }
    return render_template(
        "adiwiyata/admin/schools.html",
        schools=rows,
        search=search,
        category_titles=category_titles,
        active_nav="schools",
    )


@adiwiyata_bp.route("/admin/schools/<int:school_id>")
@role_required("admin")
def admin_adiwiyata_school_detail(school_id: int) -> Response:
    """Admin Adiwiyata — detail galeri per sekolah."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.name, s.npsn, s.jenjang, s.alamat,
                   COUNT(p.id) AS total_posts,
                   COALESCE(lk.total_likes, 0) AS total_likes
            FROM portal_schools s
            LEFT JOIN portal_adiwiyata_posts p ON p.school_id = s.id
            LEFT JOIN (
                SELECT pp.school_id, COUNT(pl.id) AS total_likes
                FROM portal_adiwiyata_posts pp
                JOIN adiwiyata_post_likes pl ON pl.post_id = pp.id AND pl.action='like'
                GROUP BY pp.school_id
            ) lk ON lk.school_id = s.id
            WHERE s.id = %s
            GROUP BY s.id, s.name, s.npsn, s.jenjang, s.alamat, lk.total_likes
            """,
            (school_id,),
        )
        school = cur.fetchone()
    if not school:
        flash("Sekolah tidak ditemukan.", "danger")
        return redirect(url_for("adiwiyata.admin_adiwiyata_schools"))
    school = dict(school)

    category = request.args.get("category", "").strip() or None
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24

    posts, total = _list_adiwiyata_posts_admin(
        school_id=school_id,
        category=category,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, -(-total // per_page))

    category_titles = {
        "pengelolaan-sampah": "Pengelolaan Sampah",
        "konservasi-energi": "Konservasi Energi",
        "konservasi-air": "Konservasi Air",
        "kebersihan-sanitasi-drainase": "Kebersihan & Sanitasi",
        "kompos": "Kompos",
        "tanaman": "Tanaman",
    }
    return render_template(
        "adiwiyata/admin/school_detail.html",
        school=school,
        posts=posts,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        selected_category=category,
        category_titles=category_titles,
        active_nav="schools",
    )


@adiwiyata_bp.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@role_required("admin")
def admin_adiwiyata_delete_post(post_id: int) -> Response:
    """Admin delete satu post adiwiyata."""
    post = get_adiwiyata_post(post_id)
    if not post:
        flash("Post tidak ditemukan.", "danger")
        return redirect(url_for("adiwiyata.admin_adiwiyata_posts"))
    school_id = post.get("school_id")
    ok = delete_adiwiyata_post(post_id)
    if ok:
        flash("Post berhasil dihapus.", "success")
    else:
        flash("Gagal menghapus post.", "danger")
    # Kembali ke halaman asal
    ref = request.form.get("redirect_to") or ""
    if ref == "school_detail" and school_id:
        return redirect(url_for("adiwiyata.admin_adiwiyata_school_detail", school_id=school_id))
    if ref == "posts":
        return redirect(url_for("adiwiyata.admin_adiwiyata_posts"))
    return redirect(url_for("adiwiyata.admin_adiwiyata_posts"))

# ===== End Admin Adiwiyata Routes =====

def make_cors_response(response_or_dict, status_code=200):
    from flask import jsonify, make_response
    if isinstance(response_or_dict, dict):
        response = jsonify(response_or_dict)
        response.status_code = status_code
    else:
        response = make_response(response_or_dict)
        response.status_code = status_code
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@adiwiyata_api_bp.route("/api/public/adiwiyata/posts", methods=["GET", "OPTIONS"])
def api_public_adiwiyata_posts():
    from flask import request
    if request.method == "OPTIONS":
        return make_cors_response({})

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 20, type=int)))
    offset = (page - 1) * per_page
    posts = list_all_adiwiyata_posts_public(limit=per_page, offset=offset)
    total = count_all_adiwiyata_posts()
    return make_cors_response({
        "posts": posts,
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": offset + per_page < total,
    })


@adiwiyata_api_bp.route("/api/public/adiwiyata/random-photos", methods=["GET", "OPTIONS"])
def api_public_adiwiyata_random_photos():
    from flask import request
    if request.method == "OPTIONS":
        return make_cors_response({})

    limit = min(30, max(1, request.args.get("limit", 12, type=int)))
    photos = list_random_adiwiyata_photos(limit=limit)
    return make_cors_response({"photos": photos})


@adiwiyata_api_bp.route("/api/public/adiwiyata/top-photos", methods=["GET", "OPTIONS"])
def api_public_adiwiyata_top_photos():
    from flask import request
    if request.method == "OPTIONS":
        return make_cors_response({})

    limit = min(30, max(1, request.args.get("limit", 6, type=int)))
    sort = request.args.get("sort", "newest")
    if sort not in ("newest", "top"):
        sort = "newest"
    photos = list_adiwiyata_photos_sorted(limit=limit, sort=sort)
    return make_cors_response({"photos": photos})


# ===== Likes & Comments API =====

def _cors_preflight():
    resp = make_response("", 204)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@adiwiyata_api_bp.route("/api/public/adiwiyata/posts/<int:post_id>/likes", methods=["GET", "POST", "OPTIONS"])
def api_adiwiyata_likes(post_id: int):
    if request.method == "OPTIONS":
        return _cors_preflight()

    if request.method == "GET":
        fingerprint = request.args.get("fp", "")
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM adiwiyata_post_likes WHERE post_id = %s AND action = 'like'", (post_id,))
            likes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM adiwiyata_post_likes WHERE post_id = %s AND action = 'dislike'", (post_id,))
            dislikes = cur.fetchone()[0]
            
            user_action = None
            if fingerprint:
                cur.execute(
                    "SELECT action FROM adiwiyata_post_likes WHERE post_id = %s AND fingerprint = %s",
                    (post_id, fingerprint[:64])
                )
                row = cur.fetchone()
                if row:
                    user_action = row["action"]
        return make_cors_response({"likes": likes, "dislikes": dislikes, "user_action": user_action})

    # POST: toggle like/dislike
    data = request.get_json(silent=True) or {}
    fingerprint = str(data.get("fingerprint", ""))[:64]
    action = str(data.get("action", ""))
    
    if not fingerprint or action not in ("like", "dislike"):
        return make_cors_response({"error": "fingerprint and valid action required"}, 400)

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT action FROM adiwiyata_post_likes WHERE post_id = %s AND fingerprint = %s",
            (post_id, fingerprint)
        )
        row = cur.fetchone()
        
        if row:
            if row["action"] == action:
                # If clicking the same action, remove it
                cur.execute(
                    "DELETE FROM adiwiyata_post_likes WHERE post_id = %s AND fingerprint = %s",
                    (post_id, fingerprint)
                )
                result_action = "removed"
            else:
                # If clicking the opposite action, switch it
                cur.execute(
                    "UPDATE adiwiyata_post_likes SET action = %s WHERE post_id = %s AND fingerprint = %s",
                    (action, post_id, fingerprint)
                )
                result_action = action
        else:
            # Insert new action
            cur.execute(
                "INSERT INTO adiwiyata_post_likes (post_id, fingerprint, action) VALUES (%s, %s, %s)",
                (post_id, fingerprint, action)
            )
            result_action = action
            
        cur.execute("SELECT COUNT(*) FROM adiwiyata_post_likes WHERE post_id = %s AND action = 'like'", (post_id,))
        likes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM adiwiyata_post_likes WHERE post_id = %s AND action = 'dislike'", (post_id,))
        dislikes = cur.fetchone()[0]

    return make_cors_response({"action": result_action, "likes": likes, "dislikes": dislikes})






@adiwiyata_bp.route("/sekolah/", strict_slashes=False)
@role_required("sekolah")
def sekolah_adiwiyata() -> Response:
    """Menu Adiwiyata untuk sekolah."""
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    subtitle = ""
    if school and school.get("name") and school.get("npsn"):
        subtitle = f"{school.get('name')} • NPSN {school.get('npsn')}"
        
    cards = [
        {
            "title": "Konservasi Energi",
            "description": "Laporan penggunaan hemat energi, panel surya, dan efisiensi listrik.",
            "icon": "bi-lightning-charge",
            "href": "#",
            "col_class": "col-md-4 col-12",
            "badge_text": "Segera Hadir",
            "badge_type": "secondary"
        },
        {
            "title": "Konservasi Air",
            "description": "Penghematan air bersih, biopori, dan pemanfaatan air hujan.",
            "icon": "bi-droplet",
            "href": "#",
            "col_class": "col-md-4 col-12",
            "badge_text": "Segera Hadir",
            "badge_type": "secondary"
        },
        {
            "title": "Kebersihan, Sanitasi, Drainase",
            "description": "Pemantauan toilet bersih, saluran air, dan lingkungan sehat.",
            "icon": "bi-stars",
            "href": "#",
            "col_class": "col-md-4 col-12",
            "badge_text": "Segera Hadir",
            "badge_type": "secondary"
        },
        {
            "title": "Kompos",
            "description": "Pembuatan pupuk organik dari sisa daun dan limbah organik sekolah.",
            "icon": "bi-recycle",
            "href": "#",
            "col_class": "col-md-4 col-12",
            "badge_text": "Segera Hadir",
            "badge_type": "secondary"
        },
        {
            "title": "Pengelolaan Sampah",
            "description": "Bank sampah, pemilahan organik/anorganik, dan daur ulang.",
            "icon": "bi-trash3",
            "href": url_for("adiwiyata.sekolah_adiwiyata_feed", category="pengelolaan-sampah"),
            "col_class": "col-md-4 col-12",
            "badge_text": "Siap Digunakan",
            "badge_type": "primary"
        },
        {
            "title": "Tanaman",
            "description": "Perawatan ruang terbuka hijau, pembibitan, dan taman sekolah.",
            "icon": "bi-tree",
            "href": "#",
            "col_class": "col-md-4 col-12",
            "badge_text": "Segera Hadir",
            "badge_type": "secondary"
        },
    ]
    return render_template(
        "role_selection.html",
        page_title="Adiwiyata - ASKA Portal",
        page_description="Menu program Adiwiyata sekolah",
        header_title="Menu Adiwiyata",
        header_subtitle=subtitle,
        cards=cards,
        default_col_class="col-md-4 col-12",
        enable_odd_center=False,
        show_logout=False,
        back_href=url_for("portal.sekolah_home"),
    )


@adiwiyata_bp.route("/sekolah/<category>")
@role_required("sekolah")
def sekolah_adiwiyata_feed(category: str) -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung dengan sekolah.", "warning")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata"))

    posts = list_adiwiyata_posts(school["id"], category)
    
    title = _adiwiyata_category_title(category)
    share_prompt = session.pop(_ADIWIYATA_SHARE_PROMPT_SESSION_KEY, None)
    if share_prompt and (
        share_prompt.get("school_id") != school["id"] or share_prompt.get("category") != category
    ):
        share_prompt = None
    try:
        user_app_notifications = fetch_user_notification_summary(
            user_id=int(user.get("id")),
            categories=list(USER_APP_NOTIFICATION_CATEGORIES),
        )
    except Exception:
        user_app_notifications = {"unread_count": 0, "total_count": 0}
    
    return render_template(
        "adiwiyata/sekolah/feed.html",
        posts=posts,
        category=category,
        title=title,
        school=school,
        is_public=False,
        adiwiyata_share_base_url=_adiwiyata_public_share_base_url(),
        share_prompt=share_prompt,
        user_app_notifications=user_app_notifications,
    )


@adiwiyata_api_bp.route("/public/sekolah/<int:school_id>/adiwiyata/<category>")
def public_sekolah_adiwiyata_feed(school_id: int, category: str) -> Response:
    school = _fetch_public_school_profile(school_id)
    if not school:
        flash("Sekolah tidak ditemukan.", "warning")
        return redirect("http://localhost:3000/adiwiyata")

    posts = list_adiwiyata_posts(school_id, category)
    
    title = _adiwiyata_category_title(category)
    
    return render_template(
        "adiwiyata/sekolah/feed.html",
        posts=posts,
        category=category,
        title=title,
        school=school,
        is_public=True,
        adiwiyata_share_base_url=_adiwiyata_public_share_base_url(),
        share_prompt=None,
    )

@adiwiyata_api_bp.route("/api/public/sekolah/<int:school_id>/adiwiyata/<category>")
def api_public_sekolah_adiwiyata_feed(school_id: int, category: str) -> Response:
    school = _fetch_public_school_profile(school_id)
    if not school:
        return jsonify({"success": False, "message": "Sekolah tidak ditemukan."}), 404

    posts = list_adiwiyata_posts(school_id, category)
    
    title = _adiwiyata_category_title(category)
    
    # posts is a list of dicts/RealDictRow. Let's make sure it's fully JSON serializable
    serialized_posts = []
    for p in posts:
        post_dict = dict(p)
        if "created_at" in post_dict and post_dict["created_at"]:
            post_dict["created_at"] = post_dict["created_at"].isoformat()
        serialized_posts.append(post_dict)
        
    return jsonify({
        "success": True,
        "school": dict(school),
        "posts": serialized_posts,
        "category": category,
        "title": title
    })


@adiwiyata_bp.route("/sekolah/<category>/add", methods=["POST"])
@role_required("sekolah")
def sekolah_adiwiyata_add(category: str) -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        return redirect(url_for("adiwiyata.sekolah_adiwiyata"))

    description = request.form.get("description", "").strip()
    if len(description) < 100:
        flash("Deskripsi wajib diisi dan minimal 100 karakter.", "warning")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=category))

    post_type = request.form.get("post_type", "image")  # "image" or "video_link"
    title = _adiwiyata_category_title(category)

    if post_type == "video_link":
        video_url = request.form.get("video_url", "").strip()
        if not video_url:
            flash("Link video tidak boleh kosong.", "warning")
            return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=category))

        # Normalize YouTube / Google Drive / generic URLs
        import re
        yt_match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})', video_url)
        if yt_match:
            video_id = yt_match.group(1)
            embed_url = f"https://www.youtube.com/embed/{video_id}"
        else:
            # Store raw URL for iframe src
            embed_url = video_url

        # Handle optional manual thumbnail
        import uuid
        thumbnail_path = None
        video_thumb_file = request.files.get("video_thumbnail")
        if video_thumb_file and video_thumb_file.filename:
            ext = video_thumb_file.filename.rsplit(".", 1)[-1].lower()
            if ext in {"png", "jpg", "jpeg", "webp"}:
                save_ext = "webp" if ext == "webp" else "jpg"
                filename = f"{uuid.uuid4().hex}_thumb.{save_ext}"
                school_id_str = str(school["id"])
                target_dir = UPLOAD_FOLDER / "adiwiyata" / school_id_str
                target_dir.mkdir(parents=True, exist_ok=True)
                filepath = target_dir / filename
                
                try:
                    from PIL import Image
                    import io
                    img = Image.open(video_thumb_file.stream)
                    img = img.convert("RGB")
                    if img.width > 800 or img.height > 800:
                        img.thumbnail((800, 800), Image.LANCZOS)
                    buf = io.BytesIO()
                    pil_fmt = "WEBP" if save_ext == "webp" else "JPEG"
                    img.save(buf, format=pil_fmt, quality=80, optimize=True)
                    buf.seek(0)
                    with open(filepath, "wb") as out_f:
                        out_f.write(buf.read())
                    thumbnail_path = f"adiwiyata/{school_id_str}/{filename}"
                except Exception as e:
                    pass

        created_post = create_adiwiyata_post(school["id"], category, embed_url, "video_link", description, user["id"], thumbnail_path=thumbnail_path)
        _queue_adiwiyata_share_prompt(created_post, school, category, title, "video")
        flash("Link video berhasil diposting.", "success")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=category))

    # Default: multiple image upload
    file_storages = request.files.getlist("media_files")
    if not file_storages or all(not f.filename for f in file_storages):
        flash("File foto wajib diunggah.", "warning")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=category))

    import uuid
    import json
    school_id_str = str(school["id"])
    target_dir = UPLOAD_FOLDER / "adiwiyata" / school_id_str
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for file_storage in file_storages:
        if not file_storage.filename:
            continue
            
        ext = file_storage.filename.rsplit(".", 1)[-1].lower()
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            flash(f"Format tidak didukung untuk file {file_storage.filename}. Gunakan JPG, PNG, atau WEBP.", "warning")
            continue

        # Simpan selalu sebagai JPEG/WebP agar bisa dikompres
        save_ext = "webp" if ext == "webp" else "jpg"
        filename = f"{uuid.uuid4().hex}.{save_ext}"
        filepath = target_dir / filename

        # Kompresi gambar dengan Pillow ke maks ~200 KB
        try:
            from PIL import Image
            import io

            img = Image.open(file_storage.stream)
            img = img.convert("RGB")

            # Resize jika resolusi terlalu besar (maks 1920px)
            max_dim = 1920
            if img.width > max_dim or img.height > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)

            # Cari kualitas yang menghasilkan file ≤ 200 KB
            target_bytes = 200 * 1024  # 200 KB
            pil_fmt = "WEBP" if save_ext == "webp" else "JPEG"
            quality = 85
            for q in (85, 75, 65, 55, 45, 35):
                buf = io.BytesIO()
                img.save(buf, format=pil_fmt, quality=q, optimize=True)
                if buf.tell() <= target_bytes:
                    quality = q
                    break

            buf.seek(0)
            with open(filepath, "wb") as out_f:
                out_f.write(buf.read())

        except Exception as compress_err:
            # Fallback: simpan apa adanya jika Pillow gagal
            file_storage.stream.seek(0)
            file_storage.save(filepath)

        media_path = f"adiwiyata/{school_id_str}/{filename}"
        saved_paths.append(media_path)

    if saved_paths:
        created_post = create_adiwiyata_post(school["id"], category, json.dumps(saved_paths), "image", description, user["id"])
        _queue_adiwiyata_share_prompt(created_post, school, category, title, "foto")
        flash(f"{len(saved_paths)} Foto berhasil diposting.", "success")
    else:
        flash("Gagal mengunggah foto.", "danger")
        
    return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=category))


@adiwiyata_bp.route("/sekolah/post/<int:post_id>/edit", methods=["POST"])
@role_required("sekolah")
def sekolah_adiwiyata_edit(post_id: int) -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    
    post = get_adiwiyata_post(post_id)
    if not post or post["school_id"] != school["id"]:
        flash("Postingan tidak ditemukan atau Anda tidak memiliki akses.", "danger")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata"))
        
    description = request.form.get("description", "").strip()
    if len(description) < 100:
        flash("Deskripsi wajib diisi dan minimal 100 karakter.", "warning")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=post["category"]))
        
    update_adiwiyata_post(post_id, description)
    
    flash("Postingan berhasil diperbarui.", "success")
    return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=post["category"]))

@adiwiyata_bp.route("/sekolah/post/<int:post_id>/delete", methods=["POST"])
@role_required("sekolah")
def sekolah_adiwiyata_delete(post_id: int) -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    
    post = get_adiwiyata_post(post_id)
    if not post or post["school_id"] != school["id"]:
        flash("Postingan tidak ditemukan atau Anda tidak memiliki akses.", "danger")
        return redirect(url_for("adiwiyata.sekolah_adiwiyata"))
        
    delete_adiwiyata_post(post_id)
    flash("Postingan berhasil dihapus.", "success")
    return redirect(url_for("adiwiyata.sekolah_adiwiyata_feed", category=post["category"]))
