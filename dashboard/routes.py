from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Iterable, Optional, Dict, List
from pathlib import Path

from knowledge_loader import GENERATED_DIR, KECERDASAN_DIR, build_kecerdasan_file, generate_clean_file, load_file_order, load_kecerdasan, save_file_order

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    session,
    current_app,
    abort,
    send_from_directory,
)
from werkzeug.datastructures import MultiDict
from psycopg2 import IntegrityError

from .auth import current_user, role_required
from reporting_flags import qa_only_mode_enabled
from utils import current_jakarta_time, to_jakarta
from .queries import (
    BULLYING_STATUSES,
    PSYCH_STATUSES,
    CORRUPTION_STATUSES,
    ChatFilters,
    fetch_all_chat_users,
    fetch_bullying_reports,
    fetch_bullying_summary,
    fetch_bullying_report_detail,
    fetch_bullying_report_basic,
    fetch_chat_logs,
    fetch_conversation_thread,
    fetch_daily_activity,
    fetch_overview_metrics,
    fetch_recent_questions,
    fetch_top_keywords,
    fetch_top_users,
    fetch_feedback_summary,
    fetch_feedback_list,
    fetch_feedback_trend,
    fetch_admin_performance_data,
    fetch_admin_activity_page,
    update_bullying_report_status,
    bulk_update_bullying_report_status,
    fetch_psych_reports,
    fetch_psych_summary,
    fetch_psych_group_reports,
    update_psych_report_status,
    bulk_update_psych_report_status,
    fetch_corruption_reports,
    fetch_corruption_summary,
    fetch_corruption_report_detail,
    bulk_update_corruption_report_status,
    update_corruption_report_status,
    fetch_twitter_overview,
    fetch_twitter_activity,
    fetch_twitter_top_users,
    chat_topic_available,
    fetch_twitter_worker_logs,
    update_no_tester_preference,
    fetch_whatsapp_link_settings,
    list_spmb_service_types,
    create_spmb_service_type,
    update_spmb_service_type,
    toggle_spmb_service_type,
    delete_spmb_service_type,
    list_spmb_table_officers,
    list_spmb_table_assignments,
    save_spmb_table_assignments,
    claim_spmb_table_assignment,
    release_spmb_table_assignment,
    create_spmb_evaluation,
    list_spmb_evaluations,
    get_spmb_evaluation_counts,
    update_spmb_evaluation,
    delete_spmb_evaluation,
    get_spmb_queue_counter,
    get_latest_spmb_queue_call,
    update_spmb_queue_counter,
    record_admin_action,
    fetch_aska_knowledge_history,
)

main_bp = Blueprint("main", __name__)
PAGE_SIZE = 50
REPORT_PAGE_SIZE = 25
TWITTER_PAGE_SIZE = 25
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _env_flag(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _reporting_enabled(kind: Optional[str] = None) -> bool:
    if qa_only_mode_enabled():
        return False

    global_enabled = bool(current_app.config.get("ASKA_REPORTING_ENABLED", False))
    if not global_enabled:
        return False
    if not kind:
        return global_enabled

    kind_map = {
        "bullying": "ASKA_REPORTING_BULLYING_ENABLED",
        "psych": "ASKA_REPORTING_PSYCH_ENABLED",
        "corruption": "ASKA_REPORTING_CORRUPTION_ENABLED",
    }
    key = kind_map.get(kind.strip().lower())
    if not key:
        return global_enabled
    return global_enabled and bool(current_app.config.get(key, True))


def _reporting_disabled_response(message: str = "Fitur pelaporan ASKA sedang dinonaktifkan.") -> Response:
    wants_json = request.is_json or request.accept_mimetypes.best == "application/json"
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.method == "POST" and (wants_json or is_ajax):
        return jsonify({"success": False, "message": message}), 403
    flash(message, "warning")
    return redirect(url_for("main.dashboard"))


def _normalize_whatsapp_link(raw_value: str) -> str:
    clean = (raw_value or "").strip()
    if not clean:
        return "https://wa.me/6282143646463"
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean.rstrip("/")
    digits = "".join(ch for ch in clean if ch.isdigit())
    if not digits:
        return "https://wa.me/6282143646463"
    if digits.startswith("0"):
        digits = f"62{digits[1:]}"
    return f"https://wa.me/{digits}"


def _parse_sort_order(value: Optional[str], default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def _parse_date_only(value: Optional[str]):
    clean = (value or "").strip()
    if not clean:
        return current_jakarta_time().date()
    try:
        return datetime.strptime(clean, "%Y-%m-%d").date()
    except ValueError:
        return current_jakarta_time().date()


def _resolve_runtime_path(value: Optional[str], default: str) -> Path:
    path = Path(value or default)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


_MD_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_FOLDER_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _.-]+")


def _normalize_relative_path(raw: Optional[str], default: str = "markdown/umum.md") -> str:
    value = (raw or "").strip()
    if not value:
        return default
    value = value.replace("\\", "/")
    segments = []
    for segment in value.split("/"):
        part = segment.strip()
        if not part or part in {".", ".."}:
            continue
        segments.append(part)
    return "/".join(segments) if segments else default


def _path_within(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _relative_path_str(target: Path) -> str:
    try:
        rel = target.relative_to(KECERDASAN_DIR)
    except ValueError:
        return ""
    text = rel.as_posix()
    return text if text != "." else ""


def _sanitize_md_basename(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if not name:
        raise ValueError("Nama berkas wajib diisi.")
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    name = name.replace(" ", "_")
    name = _MD_SANITIZE_RE.sub("_", name)
    name = name.strip("._")
    if len(name) > 80:
        name = name[:80]
    if not name:
        raise ValueError("Nama berkas tidak valid.")
    return name


def _list_knowledge_files() -> list[dict]:
    items: list[dict] = []
    if not KECERDASAN_DIR.exists():
        return items

    file_order = load_file_order()
    order_index = {rel_path: idx for idx, rel_path in enumerate(file_order)}
    default_index = len(order_index)

    for path in KECERDASAN_DIR.rglob("*.md"):
        # Skip files inside .generated/ directory
        try:
            path.relative_to(GENERATED_DIR)
            continue
        except ValueError:
            pass
        try:
            stat = path.stat()
        except OSError:
            continue
        rel_text = _relative_path_str(path)
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        items.append(
            {
                "name": path.name,
                "rel_path": rel_text,
                "size": stat.st_size,
                "updated_at": updated_at,
            }
        )

    def _sort_key(item: dict) -> tuple[int, str]:
        rel_path = item.get("rel_path") or ""
        rank = order_index.get(rel_path, default_index)
        return rank, rel_path.lower()

    items.sort(key=_sort_key)
    return items


def _list_generated_files() -> list[dict]:
    """List clean (marker-free) copies from the .generated/ directory."""
    items: list[dict] = []
    if not GENERATED_DIR.exists():
        return items
    for path in GENERATED_DIR.rglob("*.md"):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(GENERATED_DIR)
        rel_text = rel.as_posix()
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        items.append(
            {
                "name": path.name,
                "rel_path": rel_text,
                "size": stat.st_size,
                "updated_at": updated_at,
            }
        )
    items.sort(key=lambda i: (i.get("rel_path") or "").lower())
    return items


def _list_knowledge_dirs() -> list[str]:
    dirs: set[str] = {""}
    if not KECERDASAN_DIR.exists():
        return [""]
    for root, dirnames, _ in os.walk(KECERDASAN_DIR):
        rel = Path(root).relative_to(KECERDASAN_DIR)
        label = "" if rel in (Path("."), Path("")) else rel.as_posix()
        dirs.add(label)
        for subdir in dirnames:
            subpath = Path(root) / subdir
            rel_sub = subpath.relative_to(KECERDASAN_DIR)
            label_sub = "" if rel_sub in (Path("."), Path("")) else rel_sub.as_posix()
            dirs.add(label_sub)
    sorted_dirs = sorted(dirs, key=lambda value: (value != "", value.lower()))
    return sorted_dirs


def _sanitize_folder_segments(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    segments: list[str] = []
    for part in re.split(r"[\\/]+", raw):
        segment = part.strip()
        if not segment or segment in {".", ".."}:
            continue
        cleaned = _FOLDER_SANITIZE_RE.sub("_", segment)
        cleaned = cleaned.strip()
        if cleaned:
            segments.append(cleaned)
    return segments


def _resolve_folder_path(raw: Optional[str]) -> tuple[str, Path]:
    segments = _sanitize_folder_segments(raw)
    if not segments:
        return "", KECERDASAN_DIR
    rel_path = "/".join(segments)
    folder_path = KECERDASAN_DIR.joinpath(*segments)
    resolved = folder_path.resolve()
    if not _path_within(resolved, KECERDASAN_DIR):
        raise ValueError("Nama folder tidak valid.")
    return rel_path, folder_path


def _try_reload_qa_chain() -> tuple[bool, Optional[str]]:
    """Coba refresh chain QA bila modul tersedia dalam proses yang sama."""

    reloaders: list[tuple[str, object]] = []
    try:
        from web_aska.handlers import reload_qa_chain as web_reload  # type: ignore

        reloaders.append(("web", web_reload))
    except Exception:
        pass

    try:
        from handlers import reload_qa_chain as tg_reload  # type: ignore

        reloaders.append(("telegram", tg_reload))
    except Exception:
        pass

    if not reloaders:
        return False, "Fungsi reload tidak tersedia di server ini."

    last_error: Optional[str] = None
    for name, fn in reloaders:
        try:
            fn()
            return True, None
        except Exception as exc:  # pragma: no cover - hanya dipakai di runtime opsional
            last_error = f"{name}: {exc}"
            continue
    return False, last_error or "Gagal reload chain."


def _load_twitter_runtime() -> dict:
    """Kumpulkan info real-time worker Twitter dari env, state file, dan autopost list."""
    state_path = _resolve_runtime_path(os.getenv("TWITTER_STATE_PATH"), "twitter_state.json")
    autopost_path = _resolve_runtime_path(os.getenv("TWITTER_AUTOPOST_MESSAGES_PATH"), "twitter_posts.txt")
    raw_bot_user_id = os.getenv("TWITTER_USER_ID")
    bot_user_id: Optional[int]
    if raw_bot_user_id:
        try:
            bot_user_id = int(str(raw_bot_user_id).strip())
        except (TypeError, ValueError):
            bot_user_id = None
    else:
        bot_user_id = None
    raw_bot_username = (os.getenv("TWITTER_USERNAME") or "").strip()
    if raw_bot_username.startswith("@"):
        raw_bot_username = raw_bot_username[1:]
    bot_username = raw_bot_username or None

    runtime: dict = {
        "state_path": str(state_path),
        "autopost_path": str(autopost_path),
        "state_exists": state_path.exists(),
        "autopost_exists": autopost_path.exists(),
        "state_error": None,
        "autopost_error": None,
        "state": {},
        "last_seen_id": None,
        "autopost_state": {},
        "last_autopost": None,
        "autopost_entries": [],
        "autopost_total": 0,
        "autopost_rag_total": 0,
        "autopost_preview": [],
        "bot_user_id": bot_user_id,
        "bot_username": bot_username,
        "settings": {
            "mentions_enabled": _env_flag("TWITTER_MENTIONS_ENABLED", "true"),
            "autopost_enabled": _env_flag("TWITTER_AUTOPOST_ENABLED", "false"),
            "poll_interval": int(os.getenv("TWITTER_POLL_INTERVAL", "180") or 180),
            "mentions_cooldown": int(os.getenv("TWITTER_MENTIONS_COOLDOWN", "180") or 180),
            "mentions_max_results": int(os.getenv("TWITTER_MENTIONS_MAX_RESULTS", "5") or 5),
            "autopost_interval": int(os.getenv("TWITTER_AUTOPOST_INTERVAL", "3600") or 3600),
            "autopost_recent_limit": int(os.getenv("TWITTER_AUTOPOST_RECENT_LIMIT", "8") or 8),
            "max_tweet_len": int(os.getenv("TWITTER_MAX_TWEET_LEN", "280") or 280),
        },
    }

    if runtime["state_exists"]:
        try:
            with state_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                runtime["state"] = payload
                runtime["last_seen_id"] = payload.get("last_seen_id")
                autopost_state = payload.get("autopost")
                if isinstance(autopost_state, dict):
                    runtime["autopost_state"] = autopost_state
                    last_ts = autopost_state.get("last_timestamp")
                    if isinstance(last_ts, (int, float)) and last_ts > 0:
                        runtime["last_autopost"] = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            else:
                runtime["state_error"] = "Format state file tidak dikenal."
        except Exception as exc:
            runtime["state_error"] = str(exc)
    else:
        runtime["state_error"] = "File state belum dibuat oleh worker."

    entries: list[dict] = []
    if runtime["autopost_exists"]:
        try:
            text = autopost_path.read_text(encoding="utf-8")
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                is_rag = line.upper().startswith("RAG:")
                display = line[4:].strip() if is_rag else line
                entry = {
                    "raw": line,
                    "display": display,
                    "is_rag": is_rag,
                    "has_placeholders": "{{" in line and "}}" in line,
                }
                entries.append(entry)
        except Exception as exc:
            runtime["autopost_error"] = str(exc)
    else:
        runtime["autopost_error"] = "File daftar autopost belum tersedia."

    runtime["autopost_entries"] = entries
    runtime["autopost_total"] = len(entries)
    runtime["autopost_rag_total"] = sum(1 for item in entries if item.get("is_rag"))
    runtime["autopost_preview"] = entries[:8]
    if runtime.get("last_autopost"):
        runtime["last_autopost_local"] = to_jakarta(runtime["last_autopost"])
    else:
        runtime["last_autopost_local"] = None

    return runtime


@main_bp.route("/profile/no-tester", methods=["POST"])
@role_required("admin")
def toggle_no_tester() -> Response:
    user = current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    raw_enabled = payload.get("enabled")
    if isinstance(raw_enabled, str):
        enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        enabled = bool(raw_enabled)

    try:
        success = update_no_tester_preference(user["id"], enabled)
    except Exception as exc:  # pragma: no cover - surfaces to UI
        return jsonify({"success": False, "message": str(exc)}), 500

    if not success:
        return jsonify({"success": False, "message": "User preference not updated"}), 400

    session_user = session.get("user") or {}
    session_user["no_tester_enabled"] = enabled
    session["user"] = session_user


    return jsonify({"success": True, "enabled": enabled})


@main_bp.route("/")
@role_required("admin")
def index() -> Response:
    return redirect(url_for("main.admin_select_role"))


@main_bp.route("/admin/select-role")
def admin_select_role() -> Response:
    user = current_user()
    if not user:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("auth.login"))
    
    role = user.get("role", "")
    # Allow admin role only
    if role != "admin":
        flash("Halaman ini hanya untuk admin.", "danger")
        return redirect(url_for("portal.home"))
    display_name = (user.get("full_name") or user.get("email") or "").strip()
    header_title = "Selamat Datang"
    if display_name:
        header_title = f"Selamat Datang, {display_name}"
    cards = [
        {
            "title": "ASKA Insight",
            "description": "Pantau data dan ringkasan aktivitas.",
            "icon": "bi-graph-up-arrow",
            "href": url_for("main.dashboard"),
        },
        {
            "title": "PANBERSS",
            "description": "Pantau kebersihan dan sarana sekolah.",
            "icon": "bi-building",
            "href": url_for("portal.home"),
        },
        {
            "title": "Hospitality",
            "description": "Pantau dan nilai layanan hospitality.",
            "icon": "bi-house-heart",
            "href": url_for("hospitality.admin_home"),
        },
        {
            "title": "Daftar Tamu",
            "description": "Pantau kunjungan tamu sekolah.",
            "icon": "bi-person-vcard",
            "href": url_for("daftar_tamu.admin_dashboard"),
        },
        {
            "title": "Call Center",
            "description": "Pantau operasional dan pesan masuk.",
            "icon": "bi-headset",
            "href": url_for("call_center.inbox"),
        },
        {
            "title": "Adiwiyata",
            "description": "Pantau progres pelestarian lingkungan sekolah.",
            "icon": "bi-buildings",
            "icon_secondary": "bi-tree-fill",
            "href": url_for("adiwiyata.admin_adiwiyata_dashboard"),
        },
        {
            "title": "Supporter",
            "description": "Kelola task sosial media dan poin staff.",
            "icon": "bi-megaphone",
            "href": url_for("supporter.admin_dashboard"),
        },
        {
            "title": "Laporan",
            "description": "Kelola form laporan dari sekolah.",
            "icon": "bi-file-earmark-text",
            "href": url_for("laporan.admin_laporan_list"),
        },
        {
            "title": "Layanan",
            "description": "Kelola layanan publik Sudin.",
            "icon": "bi-ui-checks-grid",
            "href": url_for("cms.layanan_publik"),
        },
        {
            "title": "Coming Soon",
            "description": "Menu sedang disiapkan.",
            "icon": "bi-hourglass-split",
            "disabled": True,
        },
        {
            "title": "Coming Soon",
            "description": "Menu sedang disiapkan.",
            "icon": "bi-hourglass-split",
            "disabled": True,
        },
        {
            "title": "Coming Soon",
            "description": "Menu sedang disiapkan.",
            "icon": "bi-hourglass-split",
            "disabled": True,
        },
    ]
    default_col_class = "col-lg-3 col-md-4 col-sm-6 col-12"
    return render_template(
        "role_selection.html",
        page_title="Pilih Mode Akses - ASKA Portal",
        page_description="Pilih mode akses untuk Admin",
        header_title=header_title,
        header_subtitle="Silakan pilih layanan yang ingin Anda akses",
        cards=cards,
        default_col_class=default_col_class,
        enable_odd_center=False,
        container_class="role-selection-wide",
        show_logout=True,
    )


@main_bp.route("/api/spmb-service-types")
def api_spmb_service_types() -> Response:
    service_types = list_spmb_service_types(include_inactive=False)
    return jsonify(
        {
            "data": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "sort_order": item.get("sort_order"),
                }
                for item in service_types
            ]
        }
    )


def _serialize_spmb_evaluation(item: dict) -> dict:
    created_at = item.get("created_at")
    created_at_value = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
    return {
        "id": item.get("id"),
        "pelayanan": item.get("service_type"),
        "nomorMeja": str(item.get("table_number") or ""),
        "indikator": item.get("indicator"),
        "catatan": item.get("note") or "",
        "createdAt": created_at_value,
    }


def _serialize_spmb_queue_counter(item: dict) -> dict:
    service_date = item.get("service_date")
    updated_at = item.get("updated_at")
    return {
        "id": item.get("id"),
        "serviceDate": service_date.isoformat() if hasattr(service_date, "isoformat") else str(service_date or ""),
        "currentNumber": int(item.get("current_number") or 0),
        "updatedAt": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or ""),
    }


def _serialize_spmb_queue_call(item: Optional[dict]) -> Optional[dict]:
    if not item:
        return None
    service_date = item.get("service_date")
    called_at = item.get("called_at")
    updated_at = item.get("updated_at")
    return {
        "id": item.get("id"),
        "serviceDate": service_date.isoformat() if hasattr(service_date, "isoformat") else str(service_date or ""),
        "queueNumber": int(item.get("queue_number") or 0),
        "tableNumber": int(item.get("table_number") or 0),
        "status": item.get("status") or "",
        "officerName": item.get("officer_name") or item.get("officer_email") or "",
        "calledAt": called_at.isoformat() if hasattr(called_at, "isoformat") else str(called_at or ""),
        "updatedAt": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or ""),
        "announcement": (
            f"Nomor antrian {int(item.get('queue_number') or 0)}, "
            f"silakan menuju meja nomor {int(item.get('table_number') or 0)}."
        ),
    }


@main_bp.route("/api/spmb-evaluations", methods=["GET", "POST"])
def api_spmb_evaluations() -> Response:
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            item = create_spmb_evaluation(
                service_type=str(payload.get("pelayanan") or payload.get("service_type") or "Informasi SPMB"),
                table_number=int(payload.get("nomorMeja") or payload.get("table_number") or 0),
                indicator=str(payload.get("indikator") or payload.get("indicator") or ""),
                note=str(payload.get("catatan") or payload.get("note") or ""),
                client_ip=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
                user_agent=request.headers.get("User-Agent"),
            )
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            current_app.logger.exception("Failed to save SPMB evaluation")
            return jsonify({"success": False, "message": f"Gagal menyimpan evaluasi: {exc}"}), 500

        return jsonify({"success": True, "item": _serialize_spmb_evaluation(item)})

    try:
        limit = int(request.args.get("limit") or 100)
    except ValueError:
        limit = 100
    try:
        jakarta_now = current_jakarta_time()
        day_start = jakarta_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        items = list_spmb_evaluations(limit=limit)
        counts = get_spmb_evaluation_counts(day_start=day_start, day_end=day_end)
    except Exception as exc:
        current_app.logger.exception("Failed to fetch SPMB evaluations")
        return jsonify({"data": [], "error": f"Gagal mengambil riwayat evaluasi: {exc}"}), 500
    return jsonify({
        "data": [_serialize_spmb_evaluation(item) for item in items],
        "summary": {
            "today": counts["today_count"],
            "total": counts["total_count"],
            "date": day_start.date().isoformat(),
        },
    })


@main_bp.route("/api/spmb-evaluations/<int:evaluation_id>", methods=["PUT", "DELETE"])
def api_spmb_evaluation_item(evaluation_id: int) -> Response:
    if request.method == "PUT":
        payload = request.get_json(silent=True) or {}
        try:
            item = update_spmb_evaluation(
                evaluation_id,
                service_type=str(payload.get("pelayanan") or payload.get("service_type") or "Informasi SPMB"),
                table_number=int(payload.get("nomorMeja") or payload.get("table_number") or 0),
                indicator=str(payload.get("indikator") or payload.get("indicator") or ""),
                note=str(payload.get("catatan") or payload.get("note") or ""),
            )
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            current_app.logger.exception("Failed to update SPMB evaluation")
            return jsonify({"success": False, "message": f"Gagal memperbarui evaluasi: {exc}"}), 500

        if not item:
            return jsonify({"success": False, "message": "Data evaluasi tidak ditemukan."}), 404

        return jsonify({"success": True, "item": _serialize_spmb_evaluation(item)})

    try:
        item = delete_spmb_evaluation(evaluation_id)
    except Exception as exc:
        current_app.logger.exception("Failed to delete SPMB evaluation")
        return jsonify({"success": False, "message": f"Gagal menghapus evaluasi: {exc}"}), 500

    if not item:
        return jsonify({"success": False, "message": "Data evaluasi tidak ditemukan."}), 404

    return jsonify({"success": True, "item": _serialize_spmb_evaluation(item)})


@main_bp.route("/api/spmb-queue", methods=["GET", "POST"])
def api_spmb_queue() -> Response:
    service_date = current_jakarta_time().date()

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "").strip().lower()
        delta = 1 if action in {"increment", "plus", "tambah"} else -1 if action in {"decrement", "minus", "kurang"} else 0
        if delta == 0:
            return jsonify({"success": False, "message": "Aksi nomor antrian tidak valid."}), 400

        try:
            item = update_spmb_queue_counter(service_date=service_date, delta=delta)
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            current_app.logger.exception("Failed to update SPMB queue counter")
            return jsonify({"success": False, "message": f"Gagal memperbarui nomor antrian: {exc}"}), 500

        last_call = get_latest_spmb_queue_call(service_date)
        return jsonify({
            "success": True,
            "item": _serialize_spmb_queue_counter(item),
            "lastCall": _serialize_spmb_queue_call(last_call),
        })

    try:
        item = get_spmb_queue_counter(service_date)
        last_call = get_latest_spmb_queue_call(service_date)
    except Exception as exc:
        current_app.logger.exception("Failed to fetch SPMB queue counter")
        return jsonify({"success": False, "message": f"Gagal mengambil nomor antrian: {exc}"}), 500
    return jsonify({
        "success": True,
        "item": _serialize_spmb_queue_counter(item),
        "lastCall": _serialize_spmb_queue_call(last_call),
    })


@main_bp.route("/spmb-service-types", methods=["GET", "POST"])
@role_required("admin")
def spmb_service_types() -> Response:
    user = current_user() or {}
    if request.method == "POST":
        name = request.form.get("name", "")
        description = request.form.get("description", "")
        sort_order = _parse_sort_order(request.form.get("sort_order"))
        active = request.form.get("active") == "1"

        try:
            item = create_spmb_service_type(
                name=name,
                description=description,
                sort_order=sort_order,
                active=active,
                user_id=user.get("id"),
            )
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="CREATE",
                target_type="SPMB_SERVICE_TYPE",
                target_id=item.get("id"),
                target_name=item.get("name"),
                metadata={"description": item.get("description"), "sort_order": item.get("sort_order"), "active": item.get("active")},
            )
            flash("Jenis pelayanan berhasil ditambahkan.", "success")
        except IntegrityError:
            flash("Nama jenis pelayanan sudah terdaftar.", "warning")
        except ValueError as exc:
            flash(str(exc), "warning")
        except Exception as exc:
            current_app.logger.exception("Failed to create SPMB service type")
            flash(f"Gagal menambahkan jenis pelayanan: {exc}", "danger")
        return redirect(url_for("main.spmb_service_types"))

    service_types = list_spmb_service_types(include_inactive=True)
    active_count = sum(1 for item in service_types if item.get("active"))
    return render_template(
        "spmb_service_types.html",
        service_types=service_types,
        active_count=active_count,
    )


@main_bp.route("/spmb-service-types/<int:service_type_id>/update", methods=["POST"])
@role_required("admin")
def update_spmb_service_type_route(service_type_id: int) -> Response:
    user = current_user() or {}
    name = request.form.get("name", "")
    description = request.form.get("description", "")
    sort_order = _parse_sort_order(request.form.get("sort_order"))
    active = request.form.get("active") == "1"

    try:
        item = update_spmb_service_type(
            service_type_id=service_type_id,
            name=name,
            description=description,
            sort_order=sort_order,
            active=active,
            user_id=user.get("id"),
        )
        if not item:
            flash("Jenis pelayanan tidak ditemukan.", "warning")
        else:
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="UPDATE",
                target_type="SPMB_SERVICE_TYPE",
                target_id=item.get("id"),
                target_name=item.get("name"),
                metadata={"description": item.get("description"), "sort_order": item.get("sort_order"), "active": item.get("active")},
            )
            flash("Jenis pelayanan berhasil diperbarui.", "success")
    except IntegrityError:
        flash("Nama jenis pelayanan sudah terdaftar.", "warning")
    except ValueError as exc:
        flash(str(exc), "warning")
    except Exception as exc:
        current_app.logger.exception("Failed to update SPMB service type")
        flash(f"Gagal memperbarui jenis pelayanan: {exc}", "danger")
    return redirect(url_for("main.spmb_service_types"))


@main_bp.route("/spmb-service-types/<int:service_type_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_spmb_service_type_route(service_type_id: int) -> Response:
    user = current_user() or {}
    try:
        item = toggle_spmb_service_type(service_type_id, user_id=user.get("id"))
        if not item:
            flash("Jenis pelayanan tidak ditemukan.", "warning")
        else:
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="TOGGLE",
                target_type="SPMB_SERVICE_TYPE",
                target_id=item.get("id"),
                target_name=item.get("name"),
                metadata={"active": item.get("active")},
            )
            flash("Status jenis pelayanan berhasil diperbarui.", "success")
    except Exception as exc:
        current_app.logger.exception("Failed to toggle SPMB service type")
        flash(f"Gagal mengubah status jenis pelayanan: {exc}", "danger")
    return redirect(url_for("main.spmb_service_types"))


@main_bp.route("/spmb-service-types/<int:service_type_id>/delete", methods=["POST"])
@role_required("admin")
def delete_spmb_service_type_route(service_type_id: int) -> Response:
    user = current_user() or {}
    try:
        item = delete_spmb_service_type(service_type_id)
        if not item:
            flash("Jenis pelayanan tidak ditemukan.", "warning")
        else:
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="DELETE",
                target_type="SPMB_SERVICE_TYPE",
                target_id=item.get("id"),
                target_name=item.get("name"),
            )
            flash("Jenis pelayanan berhasil dihapus.", "success")
    except Exception as exc:
        current_app.logger.exception("Failed to delete SPMB service type")
        flash(f"Gagal menghapus jenis pelayanan: {exc}", "danger")
    return redirect(url_for("main.spmb_service_types"))


@main_bp.route("/spmb-table-assignments", methods=["GET", "POST"])
@role_required("admin")
def spmb_table_assignments() -> Response:
    user = current_user() or {}

    if request.method == "POST":
        selected_date = _parse_date_only(request.form.get("assignment_date"))
        assignments: dict[int, Optional[int]] = {}
        for table_number in range(1, 13):
            raw_user_id = (request.form.get(f"officer_{table_number}") or "").strip()
            try:
                assignments[table_number] = int(raw_user_id) if raw_user_id else None
            except ValueError:
                assignments[table_number] = None

        try:
            save_spmb_table_assignments(
                assignment_date=selected_date,
                assignments=assignments,
                updated_by=user.get("id"),
            )
            assigned_count = sum(1 for value in assignments.values() if value)
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="UPDATE",
                target_type="SPMB_TABLE_ASSIGNMENT",
                target_name=selected_date.isoformat(),
                metadata={"assignment_date": selected_date.isoformat(), "assigned_count": assigned_count},
            )
            flash("Petugas meja SPMB berhasil disimpan.", "success")
        except Exception as exc:
            current_app.logger.exception("Failed to save SPMB table assignments")
            flash(f"Gagal menyimpan petugas meja: {exc}", "danger")
        return redirect(url_for("main.spmb_table_assignments", date=selected_date.isoformat()))

    selected_date = _parse_date_only(request.args.get("date"))
    assignments = list_spmb_table_assignments(selected_date)
    officers = list_spmb_table_officers()
    return render_template(
        "spmb_table_assignments.html",
        selected_date=selected_date,
        assignments=assignments,
        officers=officers,
    )


@main_bp.route("/spmb-table-claim", methods=["GET", "POST"])
@role_required("admin", "coordinator", "staff")
def spmb_table_claim() -> Response:
    date_value = request.form.get("assignment_date") or request.args.get("date")
    if request.method == "POST":
        flash("Halaman klaim meja sudah dipindahkan ke menu Penugasan.", "info")
    return redirect(url_for("penugasan.spmb_table_claim", date=date_value))


@main_bp.route("/overview")
@role_required("admin")
def dashboard() -> Response:
    metrics = fetch_overview_metrics(window_days=7)
    chart_default_days = 30
    activity_default = fetch_daily_activity(days=chart_default_days)
    activity_long = fetch_daily_activity(days=365)
    incoming_activity_long = fetch_daily_activity(days=365, role="user")
    recent_questions = fetch_recent_questions(limit=8)
    top_users = fetch_top_users(limit=200)
    top_keywords = fetch_top_keywords(limit=10, days=30)

    chart_days: list[str] = []
    chart_values: list[int] = []
    for row in activity_default:
        day = row.get("day")
        if hasattr(day, "isoformat"):
            day_str = day.isoformat()
        else:
            day_str = str(day)
        chart_days.append(day_str)
        chart_values.append(int(row.get("messages") or 0))
    keyword_labels = [item["keyword"] for item in top_keywords]
    keyword_counts = [item["count"] for item in top_keywords]

    today_date = current_jakarta_time().date()

    def sum_period(activity_data, days: int) -> int:
        if not activity_data:
            return 0
        cutoff = today_date - timedelta(days=days - 1) if days > 1 else today_date
        total = 0
        for row in activity_data:
            day_value = row.get("day")
            if isinstance(day_value, datetime):
                day_value = day_value.date()
            elif isinstance(day_value, str):
                try:
                    day_value = datetime.fromisoformat(day_value).date()
                except ValueError:
                    continue
            if day_value and day_value >= cutoff:
                total += int(row.get("messages") or 0)
        return total

    messages_counts = {
        "today": sum_period(activity_long, 1),
        "week": sum_period(activity_long, 7),
        "month": sum_period(activity_long, 30),
        "year": sum_period(activity_long, 365),
        "all": metrics["total_messages"],
    }

    requests_counts = {
        "today": sum_period(incoming_activity_long, 1),
        "week": sum_period(incoming_activity_long, 7),
        "month": sum_period(incoming_activity_long, 30),
        "year": sum_period(incoming_activity_long, 365),
        "all": metrics["total_incoming_messages"],
    }

    whatsapp_settings = fetch_whatsapp_link_settings()
    whatsapp_link_value = (
        whatsapp_settings.get("wa_link")
        or os.getenv("ASKA_WHATSAPP_URL", "082143646463")
    )

    aska_links = {
        "tele": os.getenv("ASKA_TELEGRAM_URL", "https://t.me/tanyaaska_bot"),
        "web": os.getenv("ASKA_WEB_URL", "https://aska.sdnsembar01.sch.id/"),
        "twitter": os.getenv("ASKA_TWITTER_URL", "https://twitter.com/tanyaaska_ai"),
        "whatsapp": _normalize_whatsapp_link(whatsapp_link_value),
    }

    return render_template(
        "dashboard.html",
        generated_at=current_jakarta_time(),
        metrics=metrics,
        recent_questions=recent_questions,
        top_users=top_users,
        chart_days=chart_days,
        chart_values=chart_values,
        chart_default_days=chart_default_days,
        keyword_labels=keyword_labels,
        keyword_counts=keyword_counts,
        requests_counts=requests_counts,
        messages_counts=messages_counts,
        aska_links=aska_links,
    )


@main_bp.route("/overview/admin-performance")
@role_required("admin")
def admin_performance() -> Response:
    feature_key = (request.args.get("feature") or "all").strip().lower() or "all"
    admin_id = request.args.get("admin_id", type=int)
    action = (request.args.get("action") or "").strip().upper() or None
    target_type = (request.args.get("target_type") or "").strip().upper() or None
    search = (request.args.get("search") or "").strip() or None
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))

    data = fetch_admin_performance_data(
        feature_key=feature_key,
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        search=search,
        start=start,
        end=end,
        detail_limit=400,
    )
    return render_template(
        "admin_performance.html",
        performance=data,
    )


@main_bp.route("/overview/admin-performance/admin/<int:admin_id>/events")
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


@main_bp.route("/twitter/logs")
@role_required("admin")
def twitter_logs() -> Response:
    args: MultiDict = request.args
    page = max(1, int(args.get("page", 1)))
    range_key = args.get("range")

    start = _parse_date(args.get("start"))
    end = _parse_date(args.get("end"))
    now = current_jakarta_time()

    if range_key:
        key = range_key.lower()
        if key == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif key == "24h":
            start = now - timedelta(hours=24)
            end = now
        elif key == "7d":
            start = now - timedelta(days=7)
            end = now
        elif key == "30d":
            start = now - timedelta(days=30)
            end = now
        elif key == "90d":
            start = now - timedelta(days=90)
            end = now
        elif key == "all":
            start = None
            end = None

    role = args.get("role") or None
    if role not in {"user", "aska"}:
        role = None
    search = args.get("search") or None
    user_id = args.get("user_id")
    user_id = int(user_id) if user_id else None

    filters = ChatFilters(
        start=start,
        end=end,
        role=role,
        search=search,
        user_id=user_id,
        topic="twitter",
        channel="twitter",
    )

    topic_supported = chat_topic_available()

    offset = (page - 1) * TWITTER_PAGE_SIZE
    if topic_supported:
        records, total = fetch_chat_logs(filters=filters, limit=TWITTER_PAGE_SIZE, offset=offset)
    else:
        records, total = [], 0
    total_pages = max(1, ceil(total / TWITTER_PAGE_SIZE)) if total else 1

    runtime = _load_twitter_runtime()
    bot_user_id = runtime.get("bot_user_id")
    overview = fetch_twitter_overview(window_days=7, bot_user_id=bot_user_id)
    activity_rows = fetch_twitter_activity(days=45)
    activity_days: list[str] = []
    activity_mentions: list[int] = []
    activity_replies: list[int] = []
    for row in activity_rows:
        day_value = row.get("day")
        if isinstance(day_value, datetime):
            label = day_value.date().isoformat()
        elif hasattr(day_value, "isoformat"):
            label = day_value.isoformat()
        else:
            label = str(day_value)
        activity_days.append(label)
        activity_mentions.append(int(row.get("mentions") or 0))
        activity_replies.append(int(row.get("replies") or 0))

    top_users = fetch_twitter_top_users(limit=8)
    worker_logs = fetch_twitter_worker_logs(limit=120)

    autopost_page_total = 0
    for row in records:
        is_autopost = bool(bot_user_id and row.get("role") == "aska" and row.get("user_id") == bot_user_id)
        row["is_autopost"] = is_autopost
        row["is_reply"] = row.get("role") == "aska" and not is_autopost
        row["is_mention"] = row.get("role") == "user"
        if is_autopost:
            autopost_page_total += 1

    export_url = None
    if topic_supported:
        export_params: dict = {"topic": "twitter", "channel": "twitter"}
        if start:
            try:
                export_params["start"] = start.strftime("%Y-%m-%d")
            except Exception:
                export_params["start"] = str(start)
        if end:
            try:
                export_params["end"] = end.strftime("%Y-%m-%d")
            except Exception:
                export_params["end"] = str(end)
        if role:
            export_params["role"] = role
        if search:
            export_params["search"] = search
        if user_id:
            export_params["user_id"] = user_id
        export_url = url_for("main.export_chats", **export_params)

    if not range_key and not start and not end:
        range_key = "all"

    return render_template(
        "twitter_logs.html",
        overview=overview,
        records=records,
        total=total,
        page=page,
        total_pages=total_pages,
        filters=filters,
        selected_range=range_key,
        activity_days=activity_days,
        activity_mentions=activity_mentions,
        activity_replies=activity_replies,
        top_users=top_users,
        runtime=runtime,
        export_url=export_url,
        topic_supported=topic_supported,
        worker_logs=worker_logs,
        page_autopost_total=autopost_page_total,
    )



@main_bp.route("/notif-logs")
@role_required("admin")
def notif_logs() -> Response:
    args: MultiDict = request.args
    page = max(1, int(args.get("page", 1)))
    start = _parse_date(args.get("start"))
    end = _parse_date(args.get("end"))
    role = args.get("role") or None
    if role not in {"user", "aska"}:
        role = None
    search = args.get("search") or None
    user_id = args.get("user_id")
    user_id = int(user_id) if user_id else None

    filters = ChatFilters(
        start=start,
        end=end,
        role=role,
        search=search,
        user_id=user_id,
        topic="notif",
    )
    offset = (page - 1) * PAGE_SIZE
    records, total = fetch_chat_logs(filters=filters, limit=PAGE_SIZE, offset=offset)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return render_template(
        "notif_logs.html",
        records=records,
        total=total,
        page=page,
        total_pages=total_pages,
        filters=filters,
    )


@main_bp.route("/rag-debug-logs")
@role_required("admin")
def rag_debug_logs() -> Response:
    """Halaman log debug RAG — lihat chunk kecerdasan yang diambil per pertanyaan."""
    from rag_logger import read_rag_logs

    args: MultiDict = request.args
    page = max(1, int(args.get("page", 1)))
    search = args.get("search") or None

    offset = (page - 1) * PAGE_SIZE
    records, total = read_rag_logs(limit=PAGE_SIZE, offset=offset, search=search)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return render_template(
        "rag_debug_logs.html",
        records=records,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search,
    )


@main_bp.route("/chats")
@role_required("admin")
def chats() -> Response:
    args: MultiDict = request.args
    page = max(1, int(args.get("page", 1)))
    start = _parse_date(args.get("start"))
    end = _parse_date(args.get("end"))
    role = args.get("role") or None
    search = args.get("search") or None
    channel = (args.get("channel") or "").strip().lower() or None
    if channel not in {"telegram", "web", "twitter", "whatsapp"}:
        channel = None
    user_id = args.get("user_id")
    user_id = int(user_id) if user_id else None

    filters = ChatFilters(
        start=start,
        end=end,
        role=role,
        search=search,
        user_id=user_id,
        channel=channel,
        exclude_topic="notif",
    )
    offset = (page - 1) * PAGE_SIZE

    records, total = fetch_chat_logs(filters=filters, limit=PAGE_SIZE, offset=offset)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    export_params = {}
    if start:
        export_params["start"] = start.strftime("%Y-%m-%d")
    if end:
        export_params["end"] = end.strftime("%Y-%m-%d")
    if role:
        export_params["role"] = role
    if search:
        export_params["search"] = search
    if channel:
        export_params["channel"] = channel
    if user_id:
        export_params["user_id"] = user_id

    export_url = url_for("main.export_chats", **export_params)

    return render_template(
        "chats.html",
        records=records,
        total=total,
        page=page,
        total_pages=total_pages,
        filters=filters,
        export_url=export_url,
    )


@main_bp.route("/chats/thread/")
@role_required("admin")
def chat_thread_empty() -> Response:
    users_list = fetch_all_chat_users()
    if users_list:
        return redirect(url_for("main.chat_thread", user_id=users_list[0]["user_id"]))
    flash("No chats found.", "info")
    return redirect(url_for("main.chats"))


@main_bp.route("/chats/thread/<user_id>")
@role_required("admin")
def chat_thread(user_id: str) -> Response:
    try:
        user_id_int = int(user_id)
    except ValueError:
        flash("User ID tidak valid.", "danger")
        return redirect(url_for("main.chats"))

    messages = fetch_conversation_thread(user_id=user_id_int, limit=400)
    users_list = fetch_all_chat_users()

    # If user has no messages, but other chats exist, redirect to the first user
    if not messages and users_list:
        flash("Pengguna ini belum memiliki riwayat percakapan.", "info")
        return redirect(url_for("main.chat_thread", user_id=users_list[0]["user_id"]))
    
    # If no messages and no other users, redirect to chat list
    if not messages:
        return redirect(url_for("main.chats"))

    user = {
        "user_id": user_id_int,
        "username": messages[0].get("username") or "Unknown",
    }
    return render_template(
        "chat_thread.html", messages=messages, user=user, users_list=users_list
    )



@main_bp.route("/bullying-reports")
@role_required("admin")
def bullying_reports() -> Response:
    if not _reporting_enabled("bullying"):
        return _reporting_disabled_response()

    args: MultiDict = request.args
    raw_status = (args.get("status") or "").strip().lower() or None
    if raw_status and raw_status not in BULLYING_STATUSES:
        flash("Status filter tidak dikenal.", "warning")
        return redirect(url_for("main.bullying_reports"))

    highlight_param = args.get("highlight")
    highlight_id = None
    if highlight_param:
        try:
            highlight_id = int(highlight_param)
        except ValueError:
            highlight_id = None

    page = max(1, int(args.get("page", 1)))
    limit = REPORT_PAGE_SIZE
    offset = (page - 1) * limit

    try:
        records, total = fetch_bullying_reports(status=raw_status, limit=limit, offset=offset)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.bullying_reports"))

    summary = fetch_bullying_summary()
    total_pages = max(1, ceil(total / limit))

    return render_template(
        "bullying_reports.html",
        records=records,
        summary=summary,
        filter_status=raw_status,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=limit,
        highlight_id=highlight_id,
    )


@main_bp.route("/bullying-reports/<int:report_id>")
@role_required("admin")
def bullying_report_detail(report_id: int) -> Response:
    if not _reporting_enabled("bullying"):
        return _reporting_disabled_response()

    report = fetch_bullying_report_detail(report_id)
    if not report:
        flash("Laporan tidak ditemukan.", "warning")
        return redirect(url_for("main.bullying_reports"))
    return render_template("bullying_report_detail.html", report=report)


@main_bp.route("/bullying-reports/bulk-status", methods=["POST"])
@role_required("admin")
def bulk_update_bullying_status() -> Response:
    if not _reporting_enabled("bullying"):
        return _reporting_disabled_response()

    data = request.get_json()
    report_ids = data.get("report_ids")
    status = data.get("status")
    user = current_user()
    updated_by = user.get("full_name") or user.get("email") if user else None

    if not report_ids or not isinstance(report_ids, list):
        return jsonify({"success": False, "message": "Invalid report IDs"}), 400

    if status not in BULLYING_STATUSES and status != "undo":
        return jsonify({"success": False, "message": "Invalid status"}), 400

    try:
        if status == "undo":
            bulk_update_bullying_report_status(report_ids, "pending", updated_by)
        else:
            bulk_update_bullying_report_status(report_ids, status, updated_by)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@main_bp.route("/bullying-reports/<int:report_id>/status", methods=["POST"])
@role_required("admin")
def update_bullying_status(report_id: int) -> Response:
    if not _reporting_enabled("bullying"):
        return _reporting_disabled_response()

    action = (request.form.get("action") or "save").strip().lower()
    status_value = request.form.get("status")
    notes = request.form.get("notes") or ""
    assigned_to = request.form.get("assigned_to")
    due_at_raw = request.form.get("due_at")
    escalate_values = request.form.getlist("escalate")
    next_url = request.form.get("next") or url_for("main.bullying_reports")

    user = current_user()
    updated_by = None
    if user:
        updated_by = user.get("full_name") or user.get("email")

    existing = fetch_bullying_report_basic(report_id)
    if not existing:
        flash("Laporan tidak ditemukan atau sudah dihapus.", "warning")
        return redirect(next_url)

    if action == "reopen":
        status_value = "pending"
    elif status_value:
        status_value = status_value.strip().lower()

    escalated_param = None
    if escalate_values:
        escalated_param = escalate_values[-1].lower() in {"on", "1", "true"}

    due_at_param = due_at_raw if due_at_raw is not None else None

    if status_value == "spam":
        escalated_param = False
        due_at_param = ""
        assigned_to = ""

    try:
        updated = update_bullying_report_status(
            report_id,
            status=status_value,
            notes=notes,
            updated_by=updated_by,
            assigned_to=assigned_to,
            due_at=due_at_param,
            escalated=escalated_param,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(next_url)

    if updated:
        message = "Status laporan berhasil diperbarui."
        if action == "reopen":
            message = "Laporan dibuka kembali dan siap ditindaklanjuti."
        flash(message, "success")
    else:
        flash("Tidak ada perubahan yang disimpan.", "info")

    return redirect(next_url)


@main_bp.route("/corruption-reports")
@role_required("admin")
def corruption_reports() -> Response:
    if not _reporting_enabled("corruption"):
        return _reporting_disabled_response()

    args: MultiDict = request.args
    raw_status = (args.get("status") or "").strip().lower() or None
    if raw_status and raw_status not in CORRUPTION_STATUSES:
        flash("Status filter tidak dikenal.", "warning")
        return redirect(url_for("main.corruption_reports"))

    page = max(1, int(args.get("page", 1)))
    limit = REPORT_PAGE_SIZE
    offset = (page - 1) * limit

    try:
        records, total = fetch_corruption_reports(status=raw_status, limit=limit, offset=offset)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.corruption_reports"))

    summary = fetch_corruption_summary()
    total_pages = max(1, ceil(total / limit))

    return render_template(
        "corruption_reports.html",
        records=records,
        summary=summary,
        filter_status=raw_status,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=limit,
    )


@main_bp.route("/corruption-reports/<int:report_id>")
@role_required("admin")
def corruption_report_detail(report_id: int) -> Response:
    if not _reporting_enabled("corruption"):
        return _reporting_disabled_response()

    report = fetch_corruption_report_detail(report_id)
    if not report:
        flash("Laporan korupsi tidak ditemukan.", "warning")
        return redirect(url_for("main.corruption_reports"))
    return render_template("corruption_report_detail.html", report=report)


@main_bp.route("/corruption-reports/bulk-status", methods=["POST"])
@role_required("admin")
def bulk_update_corruption_status() -> Response:
    if not _reporting_enabled("corruption"):
        return _reporting_disabled_response()

    data = request.get_json()
    report_ids = data.get("report_ids")
    status = data.get("status")
    user = current_user()
    updated_by = user.get("full_name") or user.get("email") if user else None

    if not report_ids or not isinstance(report_ids, list):
        return jsonify({"success": False, "message": "Invalid report IDs"}), 400

    if status not in CORRUPTION_STATUSES and status != "undo":
        return jsonify({"success": False, "message": "Invalid status"}), 400

    try:
        if status == "undo":
            bulk_update_corruption_report_status(report_ids, "open", updated_by)
        else:
            bulk_update_corruption_report_status(report_ids, status, updated_by)
        if user:
            normalized_status = "open" if status == "undo" else status
            for report_id in report_ids:
                try:
                    record_admin_action(
                        user_id=user.get("id"),
                        feature_key="aska_insight",
                        action="UPDATE",
                        target_type="CORRUPTION_REPORT",
                        target_id=int(report_id),
                        target_name=f"Corruption Report #{int(report_id)}",
                        metadata={"status": normalized_status, "mode": "bulk"},
                    )
                except Exception:
                    current_app.logger.exception("Failed to log bulk corruption admin action")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@main_bp.route("/corruption-reports/<int:report_id>/status", methods=["POST"])
@role_required("admin")
def update_corruption_status(report_id: int) -> Response:
    if not _reporting_enabled("corruption"):
        return _reporting_disabled_response()

    action = (request.form.get("action") or "save").strip().lower()
    status_value = request.form.get("status")
    next_url = request.form.get("next") or url_for("main.corruption_reports")

    user = current_user()
    updated_by = user.get("full_name") or user.get("email") if user else None

    if action == "reopen":
        status_value = "open"
    
    if not status_value:
        flash("Tidak ada status yang dipilih.", "warning")
        return redirect(next_url)

    try:
        updated = update_corruption_report_status(
            report_id,
            status=status_value,
            updated_by=updated_by,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(next_url)

    if updated:
        if user:
            try:
                record_admin_action(
                    user_id=user.get("id"),
                    feature_key="aska_insight",
                    action="UPDATE",
                    target_type="CORRUPTION_REPORT",
                    target_id=report_id,
                    target_name=f"Corruption Report #{report_id}",
                    metadata={"status": status_value, "mode": action or "single"},
                )
            except Exception:
                current_app.logger.exception("Failed to log corruption admin action")
        flash("Status laporan korupsi berhasil diperbarui.", "success")
    else:
        flash("Gagal memperbarui status laporan korupsi.", "danger")

    return redirect(next_url)


@main_bp.route("/psych-reports")
@role_required("admin")
def psych_reports() -> Response:
    if not _reporting_enabled("psych"):
        return _reporting_disabled_response()

    args: MultiDict = request.args
    raw_status = (args.get("status") or "").strip().lower() or None
    raw_severity = (args.get("severity") or "").strip().lower() or None

    if raw_status and raw_status not in PSYCH_STATUSES:
        flash("Status filter tidak dikenal.", "warning")
        return redirect(url_for("main.psych_reports"))

    if raw_severity and raw_severity not in ('general', 'elevated', 'critical'):
        flash("Severity filter tidak dikenal.", "warning")
        return redirect(url_for("main.psych_reports"))

    page = max(1, int(args.get("page", 1)))
    limit = REPORT_PAGE_SIZE
    offset = (page - 1) * limit

    try:
        records, total = fetch_psych_reports(
            status=raw_status,
            severity=raw_severity,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.psych_reports"))

    summary = fetch_psych_summary()
    total_pages = max(1, ceil(total / limit))
    severity_counts = summary.get("severity", {})

    return render_template(
        "psych_reports.html",
        records=records,
        summary=summary,
        severity_counts=severity_counts,
        filter_status=raw_status,
        filter_severity=raw_severity,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=limit,
    )


@main_bp.route("/psych-reports/user/<int:user_id>")
@role_required("admin")
def psych_report_user_detail(user_id: int) -> Response:
    if not _reporting_enabled("psych"):
        return _reporting_disabled_response()

    records = fetch_psych_group_reports(user_id=user_id)
    if not records:
        flash("Tidak ada laporan konseling yang ditemukan untuk siswa ini.", "warning")
        return redirect(url_for("main.psych_reports"))

    return render_template(
        "psych_report_detail.html",
        records=records,
        user={
            "user_id": user_id,
            "username": records[0].get("username") or "Anon",
        },
    )


@main_bp.route("/psych-reports/report/<int:report_id>")
@role_required("admin")
def psych_report_single_detail(report_id: int) -> Response:
    if not _reporting_enabled("psych"):
        return _reporting_disabled_response()

    records = fetch_psych_group_reports(report_id=report_id)
    if not records:
        flash("Laporan konseling tidak ditemukan atau sudah dihapus.", "warning")
        return redirect(url_for("main.psych_reports"))

    user_id = records[0].get("user_id")
    if user_id:
        return redirect(url_for("main.psych_report_user_detail", user_id=user_id))

    return render_template(
        "psych_report_detail.html",
        records=records,
        user={
            "user_id": None,
            "username": records[0].get("username") or "Anon",
        },
    )


@main_bp.route("/psych-reports/bulk-status", methods=["POST"])
@role_required("admin")
def bulk_update_psych_status() -> Response:
    if not _reporting_enabled("psych"):
        return _reporting_disabled_response()

    data = request.get_json()
    report_ids = data.get("report_ids")
    status = data.get("status")
    user = current_user()
    updated_by = user.get("full_name") or user.get("email") if user else None

    if not report_ids or not isinstance(report_ids, list):
        return jsonify({"success": False, "message": "Invalid report IDs"}), 400

    if status not in PSYCH_STATUSES and status != "undo":
        return jsonify({"success": False, "message": "Invalid status"}), 400

    try:
        if status == "undo":
            bulk_update_psych_report_status(report_ids, "open", updated_by)
        else:
            bulk_update_psych_report_status(report_ids, status, updated_by)
        if user:
            normalized_status = "open" if status == "undo" else status
            for report_id in report_ids:
                try:
                    record_admin_action(
                        user_id=user.get("id"),
                        feature_key="aska_insight",
                        action="UPDATE",
                        target_type="PSYCH_REPORT",
                        target_id=int(report_id),
                        target_name=f"Psych Report #{int(report_id)}",
                        metadata={"status": normalized_status, "mode": "bulk"},
                    )
                except Exception:
                    current_app.logger.exception("Failed to log bulk psych admin action")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@main_bp.route("/psych-reports/<int:report_id>/status", methods=["POST"])
@role_required("admin")
def update_psych_status(report_id: int) -> Response:
    if not _reporting_enabled("psych"):
        return _reporting_disabled_response()

    status_value = (request.form.get("status") or "").strip().lower()
    next_url = request.form.get("next") or url_for("main.psych_reports")

    if status_value not in PSYCH_STATUSES:
        flash("Status laporan konseling tidak dikenal.", "warning")
        return redirect(next_url)

    user = current_user()
    updated_by = None
    if user:
        updated_by = user.get("full_name") or user.get("email")

    try:
        updated = update_psych_report_status(
            report_id,
            status_value,
            updated_by=updated_by,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(next_url)

    if updated:
        if user:
            try:
                record_admin_action(
                    user_id=user.get("id"),
                    feature_key="aska_insight",
                    action="UPDATE",
                    target_type="PSYCH_REPORT",
                    target_id=report_id,
                    target_name=f"Psych Report #{report_id}",
                    metadata={"status": status_value, "mode": "single"},
                )
            except Exception:
                current_app.logger.exception("Failed to log psych admin action")
        flash("Status laporan konseling berhasil diubah.", "success")
    else:
        flash("Laporan konseling tidak ditemukan atau tidak ada perubahan.", "info")

    return redirect(next_url)


@main_bp.route("/api/activity")
@role_required("admin")
def activity_api() -> Response:
    days = int(request.args.get("days", 14))
    activity = fetch_daily_activity(days=days)
    payload = [
        {
            "day": (row["day"].isoformat() if hasattr(row.get("day"), "isoformat") else str(row.get("day"))),
            "messages": int(row.get("messages") or 0),
        }
        for row in activity
    ]
    return jsonify(payload)


@main_bp.route("/feedback")
@role_required("admin")
def feedback() -> Response:
    args: MultiDict = request.args
    page = max(1, int(args.get("page", 1)))

    feedback_type = args.get("feedback_type") or None
    if feedback_type and feedback_type not in ("like", "dislike"):
        feedback_type = None

    start_date = _parse_date(args.get("start_date"))
    end_date = _parse_date(args.get("end_date"))

    if not start_date and not end_date:
        end_date = current_jakarta_time()
        start_date = end_date - timedelta(days=30)

    summary = fetch_feedback_summary(start_date=start_date, end_date=end_date)

    limit = REPORT_PAGE_SIZE
    offset = (page - 1) * limit
    records, total = fetch_feedback_list(
        filter_type=feedback_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    for record in records:
        if record.get("created_at"):
            record["created_at"] = to_jakarta(record["created_at"])
        if record.get("message_created_at"):
            record["message_created_at"] = to_jakarta(record["message_created_at"])

    trend_start = (end_date or current_jakarta_time()) - timedelta(days=30)
    trend_data = fetch_feedback_trend(start_date=trend_start, days=30)

    chart_days: list[str] = []
    chart_likes: list[int] = []
    chart_dislikes: list[int] = []

    for row in trend_data:
        day = row.get("day")
        day_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
        chart_days.append(day_str)
        chart_likes.append(row.get("likes", 0))
        chart_dislikes.append(row.get("dislikes", 0))

    total_pages = max(1, ceil(total / limit)) if total else 1

    return render_template(
        "feedback.html",
        summary=summary,
        records=records,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=limit,
        filter_type=feedback_type,
        start_date=start_date,
        end_date=end_date,
        chart_days=chart_days,
        chart_likes=chart_likes,
        chart_dislikes=chart_dislikes,
        generated_at=current_jakarta_time(),
    )


@main_bp.route("/chats/export")
@role_required("admin")
def export_chats() -> Response:
    args: MultiDict = request.args
    start = _parse_date(args.get("start"))
    end = _parse_date(args.get("end"))
    role = args.get("role") or None
    search = args.get("search") or None
    channel = (args.get("channel") or "").strip().lower() or None
    if channel not in {"telegram", "web", "twitter", "whatsapp"}:
        channel = None
    user_id = args.get("user_id")
    user_id = int(user_id) if user_id else None
    topic = args.get("topic") or None
    normalized_topic = (topic or "").strip().lower() or None
    if not channel and normalized_topic in {"telegram", "web", "twitter", "whatsapp"}:
        channel = normalized_topic

    filters = ChatFilters(
        start=start,
        end=end,
        role=role,
        search=search,
        user_id=user_id,
        topic=normalized_topic,
        channel=channel,
    )

    records, _ = fetch_chat_logs(filters=filters, limit=5000, offset=0)

    from io import StringIO
    import csv

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "created_at", "user_id", "username", "role", "channel", "topic", "response_time_ms", "text"])
    for row in records:
        created_at = row.get("created_at")
        if created_at:
            created_at = to_jakarta(created_at)
            try:
                created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                created_at = str(created_at)
        writer.writerow(
            [
                row.get("id"),
                created_at,
                row.get("user_id"),
                row.get("username"),
                row.get("role"),
                row.get("channel"),
                row.get("topic"),
                row.get("response_time_ms"),
                (row.get("text") or "").replace("\n", " "),
            ]
        )

    buffer.seek(0)
    filename = f"chat_logs_export_{current_jakarta_time():%Y%m%d_%H%M%S}.csv"
    response = Response(buffer.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@main_bp.route("/knowledge", methods=["GET", "POST"])
@role_required("admin")
def manage_knowledge() -> Response:
    """Halaman admin untuk menambah/mengedit berkas kecerdasan ASKA."""

    KECERDASAN_DIR.mkdir(parents=True, exist_ok=True)
    user = current_user()
    admin_id = user.get("id") if user else None
    files = _list_knowledge_files()
    default_file = files[0]["rel_path"] if files else "markdown/umum.md"
    values = request.values
    selected_file = _normalize_relative_path(values.get("file"), default=default_file)
    selected_tab = (values.get("tab") or "editor").strip().lower()
    if selected_tab not in {"editor", "history", "preview"}:
        selected_tab = "editor"
    try:
        selected_path = (KECERDASAN_DIR / selected_file).resolve()
        if not _path_within(selected_path, KECERDASAN_DIR):
            raise ValueError("Nama berkas tidak valid.")
    except Exception:
        selected_file = _normalize_relative_path(None, default=default_file)
        selected_path = (KECERDASAN_DIR / selected_file).resolve()

    selected_basename = Path(selected_file).name

    if request.method == "POST":
        action = (request.form.get("action") or "save_file").strip()

        if action == "save_file_order":
            payload = request.form.get("file_order") or ""
            raw_items = [item.strip() for item in payload.split(",") if item.strip()]
            existing_paths = {item["rel_path"] for item in files}
            ordered_paths = [path for path in raw_items if path in existing_paths]
            for item in files:
                rel_path = item["rel_path"]
                if rel_path not in ordered_paths:
                    ordered_paths.append(rel_path)
            save_file_order(ordered_paths)
            flash("Urutan berkas tersimpan.", "success")
            return redirect(url_for("main.manage_knowledge", file=selected_file))

        if action == "delete_file":
            try:
                if not selected_path.exists():
                    raise ValueError("Berkas tidak ditemukan.")
                if not _path_within(selected_path, KECERDASAN_DIR):
                    raise ValueError("Lokasi berkas tidak valid.")
                # Delete source file
                selected_path.unlink()
                # Delete clean copy if exists
                clean_path = GENERATED_DIR / Path(selected_file)
                if clean_path.exists():
                    clean_path.unlink()
                build_kecerdasan_file()
                try:
                    record_admin_action(
                        user_id=admin_id,
                        feature_key="aska_insight",
                        action="DELETE",
                        target_type="ASKA_KNOWLEDGE_FILE",
                        target_name=selected_file,
                        metadata={"path": selected_file},
                    )
                except Exception:
                    current_app.logger.exception("Failed to log knowledge file delete")
                flash(f"Berkas '{selected_file}' berhasil dihapus.", "success")
            except Exception as exc:
                flash(str(exc), "danger")
            return redirect(url_for("main.manage_knowledge"))

        if action == "append_snippet":
            raw_name = request.form.get("new_filename") or selected_basename or default_file
            content = (request.form.get("append_content") or "").rstrip()
            page_from_raw = (request.form.get("page_from") or "").strip()
            page_to_raw = (request.form.get("page_to") or "").strip()
            try:
                if not content:
                    raise ValueError("Konten potongan baru wajib diisi.")
                sanitized_name = _sanitize_md_basename(raw_name)
                target_path = KECERDASAN_DIR / sanitized_name
                resolved_target = target_path.resolve()
                if not _path_within(resolved_target, KECERDASAN_DIR):
                    raise ValueError("Lokasi berkas tidak valid.")
                existed_before = target_path.exists()
                if not existed_before:
                    raise ValueError("Berkas belum ada. Simpan dulu berkasnya sebelum menambah potongan halaman.")

                page_from: Optional[int] = None
                page_to: Optional[int] = None
                if page_from_raw:
                    page_from = int(page_from_raw)
                if page_to_raw:
                    page_to = int(page_to_raw)
                if page_from is not None and page_to is not None and page_from > page_to:
                    raise ValueError("Range halaman tidak valid (dari > sampai).")

                existing_text = target_path.read_text(encoding="utf-8")
                snippet = content.strip()
                if snippet and snippet in existing_text:
                    flash("Konten yang sama sudah ada di berkas (anti duplikat aktif).", "warning")
                    return redirect(
                        url_for(
                            "main.manage_knowledge",
                            file=str(target_path.relative_to(KECERDASAN_DIR)).replace("\\", "/"),
                        )
                    )

                # Build the new block with a page marker
                new_page_num = page_from  # use page_from as sort key
                if new_page_num is not None:
                    page_label = f"{page_from}" if page_to is None or page_from == page_to else f"{page_from}-{page_to}"
                    new_block = f"<!-- halaman:{page_label} -->\n{content.rstrip()}\n"
                else:
                    new_block = content.rstrip() + "\n"

                if new_page_num is not None:
                    # Split existing text into blocks by page markers and
                    # insert the new block in sorted order.
                    import re as _re
                    marker_pattern = _re.compile(r"^<!-- halaman:(\d+)(?:-(\d+))? -->", _re.MULTILINE)
                    markers = list(marker_pattern.finditer(existing_text))

                    # Check for duplicate/overlapping page numbers
                    req_from = page_from
                    req_to = page_to if page_to is not None else page_from
                    for m in markers:
                        existing_from = int(m.group(1))
                        existing_to = int(m.group(2)) if m.group(2) else existing_from
                        # Check overlap: two ranges overlap if start1 <= end2 AND start2 <= end1
                        if req_from <= existing_to and existing_from <= req_to:
                            existing_label = f"{existing_from}" if existing_from == existing_to else f"{existing_from}-{existing_to}"
                            flash(f"Halaman {page_label} tumpang tindih dengan halaman {existing_label} yang sudah ada.", "warning")
                            return redirect(
                                url_for(
                                    "main.manage_knowledge",
                                    file=str(target_path.relative_to(KECERDASAN_DIR)).replace("\\", "/"),
                                )
                            )

                    if markers:
                        insert_pos = None
                        for m in markers:
                            m_page = int(m.group(1))
                            if m_page > new_page_num:
                                insert_pos = m.start()
                                break
                        if insert_pos is not None:
                            # Insert before the marker with higher page number
                            before = existing_text[:insert_pos].rstrip()
                            after = existing_text[insert_pos:].lstrip("\n")
                            new_text = before + "\n\n" + new_block + "\n" + after
                        else:
                            # All existing markers have lower page numbers; append at end
                            new_text = existing_text.rstrip() + "\n\n" + new_block
                    else:
                        # No markers yet — just append
                        new_text = existing_text.rstrip() + "\n\n" + new_block
                else:
                    # No page number — plain append
                    new_text = existing_text.rstrip() + "\n\n" + new_block

                target_path.write_text(new_text, encoding="utf-8")

                generate_clean_file(target_path)
                build_kecerdasan_file()
                relative_path = str(target_path.relative_to(KECERDASAN_DIR)).replace("\\", "/")
                metadata = {
                    "path": relative_path,
                    "folder": "",
                    "chars": len(content),
                    "refreshed": False,
                    "page_from": page_from,
                    "page_to": page_to,
                    "append": True,
                }
                try:
                    record_admin_action(
                        user_id=admin_id,
                        feature_key="aska_insight",
                        action="UPDATE",
                        target_type="ASKA_KNOWLEDGE_FILE",
                        target_name=relative_path,
                        metadata=metadata,
                    )
                except Exception:
                    current_app.logger.exception("Failed to log knowledge snippet append")
                flash("Potongan halaman berhasil ditambahkan ke berkas.", "success")
                return redirect(url_for("main.manage_knowledge", file=relative_path))
            except Exception as exc:
                flash(str(exc), "danger")
                return redirect(url_for("main.manage_knowledge", file=selected_file))

        raw_name = request.form.get("new_filename") or selected_basename or default_file
        content = (request.form.get("content") or "").rstrip()
        refresh_requested = request.form.get("refresh") == "1"
        try:
            sanitized_name = _sanitize_md_basename(raw_name)
            target_path = KECERDASAN_DIR / sanitized_name
            resolved_target = target_path.resolve()
            if not _path_within(resolved_target, KECERDASAN_DIR):
                raise ValueError("Lokasi berkas tidak valid.")
            existed_before = target_path.exists()
            target_path.write_text(content + "\n", encoding="utf-8")

            generate_clean_file(target_path)
            build_kecerdasan_file()
            relative_path = str(target_path.relative_to(KECERDASAN_DIR)).replace("\\", "/")
            metadata = {
                "path": relative_path,
                "folder": "",
                "chars": len(content),
                "refreshed": refresh_requested,
                "page_from": None,
                "page_to": None,
                "append": False,
            }
            try:
                record_admin_action(
                    user_id=admin_id,
                    feature_key="aska_insight",
                    action="CREATE" if not existed_before else "UPDATE",
                    target_type="ASKA_KNOWLEDGE_FILE",
                    target_name=relative_path,
                    metadata=metadata,
                )
            except Exception:
                current_app.logger.exception("Failed to log knowledge file edit")
            flash(f"Berkas kecerdasan '{relative_path}' tersimpan.", "success")
            if refresh_requested:
                ok, message = _try_reload_qa_chain()
                if ok:
                    flash("Knowledge base berhasil direfresh untuk ASKA.", "success")
                else:
                    flash(f"Berkas tersimpan, tetapi gagal refresh otomatis: {message}", "warning")
            return redirect(url_for("main.manage_knowledge", file=relative_path))
        except Exception as exc:
            flash(str(exc), "danger")

    is_new_mode = values.get("new") == "1"
    selected_content = ""
    selected_content_clean = ""
    if is_new_mode:
        selected_basename = ""
    elif selected_path.exists() and selected_path.suffix.lower() == ".md":
        try:
            selected_content = selected_path.read_text(encoding="utf-8")
        except Exception:
            selected_content = ""
        # Read clean version for preview
        try:
            clean_path = GENERATED_DIR / Path(selected_file)
            if clean_path.exists():
                selected_content_clean = clean_path.read_text(encoding="utf-8")
            else:
                selected_content_clean = selected_content
        except Exception:
            selected_content_clean = selected_content

    combined_preview = load_kecerdasan()
    combined_chars = len(combined_preview)
    combined_preview_snippet = combined_preview[:1200]

    history_entries = fetch_aska_knowledge_history(file_path=selected_file, limit=50)

    return render_template(
        "manage_knowledge.html",
        files=files,
        generated_files=_list_generated_files(),
        selected_file=selected_file,
        selected_basename=selected_basename,
        selected_content=selected_content,
        selected_content_clean=selected_content_clean,
        selected_tab=selected_tab,
        history_entries=history_entries,
        combined_chars=combined_chars,
        combined_preview_snippet=combined_preview_snippet,
    )


@main_bp.route("/documentation")
def documentation() -> Response:
    return redirect(url_for("main.doc_email_setup"))


@main_bp.route("/documentation/email-setup")
def doc_email_setup() -> Response:
    return render_template("documentation/email_setup.html")


@main_bp.route("/documentation/tutorial-portal")
def doc_tutorial_portal() -> Response:
    return render_template("documentation/tutorial_ppt.html")


GUIDE_BOOK_FILES = {
    "Role Admin.pdf",
    "Role Sekolah.pdf",
    "Role Koordinator.pdf",
    "Role Tim Penilai.pdf",
}


@main_bp.route("/documentation/guide-book/<path:filename>")
def doc_guide_book(filename: str) -> Response:
    if filename not in GUIDE_BOOK_FILES:
        abort(404)
    guide_book_dir = Path(__file__).resolve().parent / "templates" / "documentation" / "Guide_Book"
    return send_from_directory(guide_book_dir, filename)


@main_bp.route("/documentation/tutorial-portal/admin")
def doc_tutorial_role_admin() -> Response:
    return render_template("documentation/tutorial_role_admin.html")


@main_bp.route("/documentation/tutorial-portal/sekolah")
def doc_tutorial_role_sekolah() -> Response:
    return render_template("documentation/tutorial_role_sekolah.html")


@main_bp.route("/documentation/tutorial-portal/koordinator")
def doc_tutorial_role_koordinator() -> Response:
    return render_template("documentation/tutorial_role_koordinator.html")


@main_bp.route("/documentation/tutorial-portal/tim-penilai")
def doc_tutorial_role_tim_penilai() -> Response:
    return render_template("documentation/tutorial_role_tim_penilai.html")
