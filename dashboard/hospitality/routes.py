from __future__ import annotations

from datetime import date, datetime
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from dashboard.auth import current_user, role_required
from dashboard.db_access import get_cursor
from dashboard.daftar_tamu.queries import (
    create_user_notifications,
    HOSPITALITY_NOTIFICATION_CATEGORY,
)
from dashboard.telegram_notifications import (
    notify_reopen_request,
    notify_reopen_status_update,
)
from dashboard.portal.routes import _fetch_user_school, inject_permissions as portal_inject_permissions
from .queries import (
    HOSPITALITY_SCORE_MAX,
    create_assessment,
    create_component,
    create_hosp_aspect,
    create_comment,
    create_reopen_request,
    get_latest_reopen_request_id,
    delete_component,
    delete_hosp_aspect,
    get_assessment,
    get_assessment_scores,
    get_draft_assessment,
    get_latest_assessment_for_staff_school,
    get_latest_draft_assessment_for_staff,
    get_component,
    get_hosp_aspect,
    get_latest_reopen_request,
    get_guestbook_review_detail,
    fetch_guestbook_review_bottom_schools,
    fetch_guestbook_review_rating_distribution,
    fetch_guestbook_review_stats,
    fetch_guestbook_review_top_schools,
    fetch_guestbook_review_trend,
    fetch_guestbook_review_school_rankings,
    fetch_guestbook_reviews_export,
    list_guestbook_reviews,
    list_assessments_for_school,
    list_assessments_for_staff,
    list_components_with_aspects,
    list_guestbook_candidates,
    list_comments,
    list_reopen_requests,
    link_guestbook_transaction,
    reverify_assessment,
    reorder_components,
    reorder_hosp_aspects,
    submit_assessment,
    delete_draft_assessment,
    delete_assessment,
    delete_guestbook_review,
    grant_hospitality_preview_access,
    has_hospitality_preview_access,
    list_assessments_for_preview,
    list_hospitality_preview_access_users,
    list_hospitality_preview_candidates,
    toggle_aspect_active,
    toggle_aspect_required,
    toggle_component_active,
    toggle_component_required,
    revoke_hospitality_preview_access,
    update_component,
    update_hosp_aspect,
    update_reopen_request_status,
    upsert_scores,
    log_activity,
    fetch_activity_logs,
    fetch_all_assessed_schools,
    list_guestbook_extra_questions,
    create_guestbook_extra_question,
    get_guestbook_extra_question,
    update_guestbook_extra_question,
    delete_guestbook_extra_question,
    toggle_guestbook_extra_question_active,
    reorder_guestbook_extra_questions,
)

hospitality_bp = Blueprint(
    "hospitality",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/hospitality",
)

# Roles that are allowed to perform hospitality assessments (staff-like flow).
ASSESSOR_ROLES = ("staff", "coordinator", "admin")

# Reuse portal context (permissions, badges, etc.) so base_portal works on hospitality pages.
@hospitality_bp.context_processor
def inject_portal_context():
    context = portal_inject_permissions() or {}
    user = current_user() or {}
    user_id = int(user.get("id") or 0)
    can_preview = bool(user_id and has_hospitality_preview_access(user_id=user_id))
    context["can_preview_hospitality"] = can_preview
    return context


# ===== Helper =====

_HOSPITALITY_DATE_MODE_KEY = "hospitality_date_mode"


def _use_tanggal_edit() -> bool:
    """Return True if the current session uses `tanggal_edit` for date display (default: True)."""
    mode = session.get(_HOSPITALITY_DATE_MODE_KEY, "edit")
    return str(mode).lower() != "original"



def _school_user_ids(school_id: int) -> List[int]:
    if not school_id:
        return []
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM dashboard_users
            WHERE role = 'sekolah' AND school_id = %s AND account_status = 'approved'
            """,
            (school_id,),
        )
        return [int(row["id"]) for row in cur.fetchall() if row.get("id")]


def _school_by_id(school_id: int) -> Optional[Dict[str, Any]]:
    if not school_id:
        return None
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, npsn, jenjang, alamat, active
            FROM portal_schools
            WHERE id = %s
            LIMIT 1
            """,
            (school_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _parse_guestbook_date(raw_value: Optional[str]) -> Optional[date]:
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _list_active_schools(*, limit: int = 500) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 500), 2000))
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, npsn, jenjang
            FROM portal_schools
            WHERE active = TRUE
            ORDER BY name ASC
            LIMIT %s
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _guestbook_review_scope_for_user(user: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[int]]:
    role = (user.get("role") or "").strip().lower()
    if role == "sekolah":
        school = _fetch_user_school(user.get("id"))
        if not school:
            return None, None
        return dict(school), int(school.get("id"))
    return None, None


def _hospitality_required_aspect_count() -> int:
    components = list_components_with_aspects(active_only=True)
    return sum(len(comp.get("aspects") or []) for comp in components)


def _hospitality_scored_aspect_count(assessment_id: int) -> int:
    scores = get_assessment_scores(assessment_id)
    scored_aspects = {
        int(item["aspect_id"])
        for item in scores
        if item.get("aspect_id") is not None and item.get("score") is not None
    }
    return len(scored_aspects)


def _can_preview_hospitality(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    user_id = int(user.get("id") or 0)
    return bool(user_id and has_hospitality_preview_access(user_id=user_id))


def _hospitality_preview_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login", next=request.path))
        if not _can_preview_hospitality(user):
            flash("Anda tidak memiliki akses preview hospitality.", "danger")
            return redirect(url_for("portal.home"))
        return view(*args, **kwargs)

    return wrapper


# ===== Routing =====


@hospitality_bp.route("/")
def landing() -> Response:
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    role = (user.get("role") or "").lower()
    if role == "admin":
        return redirect(url_for("hospitality.admin_home"))
    if role in ASSESSOR_ROLES:
        return redirect(url_for("hospitality.staff_home"))
    if role == "sekolah":
        return redirect(url_for("hospitality.school_home"))
    if _can_preview_hospitality(user):
        return redirect(url_for("hospitality.preview_home"))
    return redirect(url_for("hospitality.admin_home"))


@hospitality_bp.route("/staff")
@role_required(*ASSESSOR_ROLES)
def staff_home() -> Response:
    user = current_user()
    status_filter = (request.args.get("status") or "").strip().lower() or None
    search = (request.args.get("q") or "").strip() or None
    assessments = list_assessments_for_staff(
        staff_id=int(user.get("id")),
        status=status_filter,
        search=search,
    )
    draft_assessment = get_latest_draft_assessment_for_staff(staff_id=int(user.get("id")))
    if draft_assessment and (not status_filter or status_filter == "draft"):
        draft_id = draft_assessment.get("id")
        assessments = [item for item in assessments if item.get("id") != draft_id]
        assessments = [draft_assessment] + assessments
    return render_template(
        "hospitality/staff/list.html",
        assessments=assessments,
        draft_assessment=draft_assessment,
        score_max=HOSPITALITY_SCORE_MAX,
        status_filter=status_filter or "",
        search_query=search or "",
    )


@hospitality_bp.route("/staff/assess/<int:school_id>", methods=["GET", "POST"])
@role_required(*ASSESSOR_ROLES)
def staff_assess(school_id: int) -> Response:
    user = current_user()
    components = list_components_with_aspects(active_only=True)
    school = None
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, npsn, jenjang FROM portal_schools WHERE id = %s",
            (school_id,),
        )
        school = cur.fetchone()
    if not school:
        abort(404)

    assessment = get_draft_assessment(school_id=school_id, staff_id=int(user.get("id")))
    if not assessment:
        assessment = get_latest_assessment_for_staff_school(school_id=school_id, staff_id=int(user.get("id")))
    if not assessment:
        assessment = create_assessment(
            school_id=school_id,
            staff_id=int(user.get("id")),
            score_scale_max=HOSPITALITY_SCORE_MAX,
            note_text=None,
        )

    if request.method == "POST":
        note_text = (request.form.get("note") or "").strip() or None
        status_action = (request.form.get("action") or "draft").strip().lower()
        try:
            scores_payload: List[Dict[str, Any]] = []
            for comp in components:
                for aspect in comp.get("aspects") or []:
                    field = f"score_{aspect['id']}"
                    raw = request.form.get(field)
                    if raw is None:
                        continue
                    try:
                        score_val = int(raw)
                    except (TypeError, ValueError):
                        continue
                    scores_payload.append(
                        {
                            "component_id": comp["id"],
                            "aspect_id": aspect["id"],
                            "score": score_val,
                            "note": None,
                        }
                    )
            upsert_scores(assessment_id=int(assessment["id"]), scores=scores_payload)
            if status_action == "submit":
                submit_assessment(
                    assessment_id=int(assessment["id"]),
                    note_text=note_text,
                    score_scale_max=HOSPITALITY_SCORE_MAX,
                )
                flash("Penilaian tersimpan dan dikirim.", "success")
                return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment["id"]))
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    UPDATE hospitality_assessments
                    SET note_text = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (note_text, int(assessment["id"])),
                )
            flash("Draft penilaian disimpan.", "success")
            return redirect(url_for("hospitality.staff_assess", school_id=school_id))
        except Exception as exc:  # pragma: no cover
            flash(str(exc), "danger")

    assessment_scores = get_assessment_scores(int(assessment["id"])) if assessment else []
    scores_map = {s.get("aspect_id"): s.get("score") for s in assessment_scores}
    notes_by_component = {s.get("component_id"): s.get("note") for s in assessment_scores if s.get("note")}

    return render_template(
        "hospitality/staff/assess.html",
        school=school,
        components=components,
        assessment=assessment,
        assessment_status=assessment.get("status") if assessment else "draft",
        scores_map=scores_map,
        notes_by_component=notes_by_component,
        score_scale=list(range(1, HOSPITALITY_SCORE_MAX + 1)),
    )


@hospitality_bp.route("/staff/draft/<int:assessment_id>/delete", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def staff_delete_draft(assessment_id: int) -> Response:
    user = current_user()
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("staff_id") or 0) != int(user.get("id")):
        return jsonify({"success": False, "message": "Penilaian tidak ditemukan."}), 404
    if (assessment.get("status") or "").lower() != "draft":
        return jsonify({"success": False, "message": "Hanya draft yang dapat dihapus."}), 400
    try:
        delete_draft_assessment(assessment_id=assessment_id)
    except ValueError as exc:  # pragma: no cover
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True})


@hospitality_bp.route("/admin/assessment/<int:assessment_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_assessment(assessment_id: int) -> Response:
    user = current_user()
    assessment = get_assessment(assessment_id)
    school_name = (assessment or {}).get("school_name", f"ID {assessment_id}")
    try:
        deleted = delete_assessment(assessment_id=assessment_id, deleted_by=int(user.get("id")))
        if deleted:
            log_activity(
                user_id=int(user.get("id")),
                action="delete",
                target_type="HOSPITALITY_ASSESSMENT",
                target_id=assessment_id,
                target_name=school_name,
                details={"description": f"Menghapus penilaian hospitality sekolah {school_name}", "assessment_id": assessment_id, "status": (assessment or {}).get('status')},
            )
            flash("Penilaian hospitality berhasil dihapus.", "success")
        else:
            flash("Penilaian hospitality tidak ditemukan.", "warning")
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
    fallback = url_for("hospitality.admin_home")
    referrer = request.referrer or ""
    return redirect(referrer if referrer.startswith(request.host_url) else fallback)


@hospitality_bp.route("/staff/assess/<int:school_id>/score", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def staff_save_score(school_id: int) -> Response:
    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
        aspect_id = int(data.get("aspect_id"))
        component_id = int(data.get("component_id"))
        score = int(data.get("score"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data tidak valid"}), 400
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404
    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim."}), 400
    try:
        upsert_scores(
            assessment_id=assessment_id,
            scores=[{"component_id": component_id, "aspect_id": aspect_id, "score": score, "note": None}],
        )
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@hospitality_bp.route("/staff/assess/<int:school_id>/note", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def staff_save_note(school_id: int) -> Response:
    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data tidak valid"}), 400
    note = (data.get("note") or "").strip() or None
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404
    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim."}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE hospitality_assessments SET note_text = %s, updated_at = NOW() WHERE id = %s",
            (note, assessment_id),
        )
    return jsonify({"success": True})


@hospitality_bp.route("/staff/assess/<int:school_id>/draft", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def staff_save_draft(school_id: int) -> Response:
    assessment_id = request.form.get("assessment_id", type=int)
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("hospitality.staff_assess", school_id=school_id))
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        flash("Assessment tidak ditemukan.", "danger")
        return redirect(url_for("hospitality.staff_assess", school_id=school_id))
    if assessment.get("status") != "draft":
        flash("Penilaian sudah dikirim.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))
    flash("Draft penilaian disimpan.", "success")
    return redirect(url_for("hospitality.staff_assess", school_id=school_id))


@hospitality_bp.route("/staff/assess/<int:school_id>/submit", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def staff_submit_assessment(school_id: int) -> Response:
    assessment_id = request.form.get("assessment_id", type=int)
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("hospitality.staff_assess", school_id=school_id))
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        flash("Assessment tidak ditemukan.", "danger")
        return redirect(url_for("hospitality.staff_assess", school_id=school_id))
    if assessment.get("status") != "draft":
        flash("Penilaian sudah dikirim.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))
    required_aspects = _hospitality_required_aspect_count()
    scored_aspects = _hospitality_scored_aspect_count(assessment_id)
    if required_aspects > 0 and scored_aspects < required_aspects:
        flash("Semua aspek harus dinilai sebelum submit.", "warning")
        return redirect(url_for("hospitality.staff_assess", school_id=school_id))
    submit_assessment(
        assessment_id=assessment_id,
        note_text=assessment.get("note_text"),
        score_scale_max=HOSPITALITY_SCORE_MAX,
    )
    flash("Penilaian tersimpan dan dikirim.", "success")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))


@hospitality_bp.route("/assessment/<int:assessment_id>")
@role_required("staff", "admin", "coordinator")
def assessment_detail(assessment_id: int) -> Response:
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    user = current_user()
    if user.get("role") in ("staff", "coordinator") and int(user.get("id")) != int(assessment.get("staff_id")):
        abort(403)
    scores = get_assessment_scores(assessment_id)
    components = list_components_with_aspects(active_only=False)
    scores_map = {s.get("aspect_id"): s for s in scores}
    guestbook_options = list_guestbook_candidates(
        school_id=int(assessment.get("school_id")),
        user_id=int(user.get("id")) if user.get("role") in ASSESSOR_ROLES else None,
    )
    comments = list_comments(assessment_id)
    latest_reopen_request = get_latest_reopen_request(assessment_id)

    return render_template(
        "hospitality/detail.html",
        assessment=assessment,
        components=components,
        scores_map=scores_map,
        guestbook_options=guestbook_options,
        comments=comments,
        latest_reopen_request=latest_reopen_request,
        user_role=user.get("role"),
        is_staff=user.get("role") in ASSESSOR_ROLES,
        is_school=user.get("role") == "sekolah",
    )


@hospitality_bp.route("/assessment/<int:assessment_id>/link-guestbook", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def link_guestbook(assessment_id: int) -> Response:
    user = current_user()
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    if int(assessment.get("staff_id")) != int(user.get("id")):
        abort(403)

    transaction_id = request.form.get("transaction_id", type=int)
    if not transaction_id:
        flash("Pilih kunjungan buku tamu.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))

    try:
        result = link_guestbook_transaction(
            assessment_id=assessment_id,
            transaction_id=transaction_id,
            linked_by=int(user.get("id")),
        )
        if result.get("already_processed"):
            return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))

        # Notify school users and staff
        recipients = set(_school_user_ids(assessment.get("school_id")))
        recipients.add(int(user.get("id")))
        create_user_notifications(
            recipient_ids=list(recipients),
            category=HOSPITALITY_NOTIFICATION_CATEGORY,
            title="Hospitality terverifikasi",
            message="Penilaian sudah dikaitkan dengan buku tamu dan terverifikasi.",
            reference_table="hospitality_assessments",
            reference_id=assessment_id,
            link=url_for("hospitality.assessment_detail", assessment_id=assessment_id),
            metadata={"transaction_id": transaction_id},
        )
        flash("Berhasil menghubungkan buku tamu dan memverifikasi penilaian.", "success")
        log_activity(
            user_id=int(user.get("id")),
            action="verify_with_guestbook",
            target_type="HOSPITALITY_ASSESSMENT",
            target_id=assessment_id,
            target_name=(assessment or {}).get("school_name", f"ID {assessment_id}"),
            details={"description": f"Memverifikasi penilaian dengan buku tamu (ID transaksi: {transaction_id})", "transaction_id": transaction_id},
        )
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))


@hospitality_bp.route("/assessment/<int:assessment_id>/reverify", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def reverify(assessment_id: int) -> Response:
    """Re-verify an assessment that is 'submitted' but already has a guestbook link."""
    user = current_user()
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    if user.get("role") in ("staff", "coordinator") and int(user.get("id")) != int(assessment.get("staff_id")):
        abort(403)

    try:
        reverify_assessment(assessment_id=assessment_id)
        recipients = set(_school_user_ids(assessment.get("school_id")))
        recipients.add(int(user.get("id")))
        create_user_notifications(
            recipient_ids=list(recipients),
            category=HOSPITALITY_NOTIFICATION_CATEGORY,
            title="Hospitality terverifikasi ulang",
            message="Penilaian telah diverifikasi ulang dengan buku tamu yang sebelumnya terhubung.",
            reference_table="hospitality_assessments",
            reference_id=assessment_id,
            link=url_for("hospitality.assessment_detail", assessment_id=assessment_id),
        )
        log_activity(
            user_id=int(user.get("id")),
            action="reverify",
            target_type="HOSPITALITY_ASSESSMENT",
            target_id=assessment_id,
            target_name=assessment.get("school_name", f"ID {assessment_id}"),
            details={"description": f"Verifikasi ulang penilaian {assessment.get('school_name', '')}", "transaction_id": assessment.get("guestbook_transaction_id")},
        )
        flash("Penilaian berhasil diverifikasi ulang.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))


@hospitality_bp.route("/assessment/<int:assessment_id>/comment", methods=["POST"])
@role_required("staff", "sekolah", "admin", "coordinator")
def add_comment(assessment_id: int) -> Response:
    user = current_user()
    message = (request.form.get("message") or "").strip()
    parent_id = request.form.get("parent_id", type=int)
    try:
        comment = create_comment(
            assessment_id=assessment_id,
            author_user_id=int(user.get("id")),
            author_role=user.get("role"),
            message=message,
            parent_comment_id=parent_id,
        )
        recipients = set()
        assessment = get_assessment(assessment_id)
        if assessment:
            recipients.update(_school_user_ids(assessment.get("school_id")))
            recipients.add(int(assessment.get("staff_id")))
        create_user_notifications(
            recipient_ids=list(recipients),
            category=HOSPITALITY_NOTIFICATION_CATEGORY,
            title="Komentar baru penilaian hospitality",
            message=message[:120],
            reference_table="hospitality_assessments",
            reference_id=assessment_id,
            link=url_for("hospitality.assessment_detail", assessment_id=assessment_id),
        )
        flash("Komentar ditambahkan.", "success")
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id) + "#comments")


@hospitality_bp.route("/assessment/<int:assessment_id>/reopen", methods=["POST"])
@role_required(*ASSESSOR_ROLES)
def request_reopen(assessment_id: int) -> Response:
    user = current_user()
    reason = (request.form.get("reason") or "").strip() or None
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    if user.get("role") in ASSESSOR_ROLES and int(user.get("id")) != int(assessment.get("staff_id")):
        abort(403)

    req = create_reopen_request(assessment_id=assessment_id, staff_id=int(user.get("id")), reason=reason)
    if req:
        recipients = set()
        recipients.update(_school_user_ids(assessment.get("school_id")))
        recipients.add(int(assessment.get("staff_id")))
        create_user_notifications(
            recipient_ids=list(recipients),
            category=HOSPITALITY_NOTIFICATION_CATEGORY,
            title="Permintaan reopen hospitality",
            message=reason or "Permintaan reopen diajukan.",
            reference_table="hospitality_assessments",
            reference_id=assessment_id,
            link=url_for("hospitality.assessment_detail", assessment_id=assessment_id),
        )
        notify_reopen_request(
            request_id=req.get("id"),
            assessment_id=assessment_id,
            school_name=assessment.get("school_name"),
            period_name=None,
            staff_name=assessment.get("staff_name"),
            requested_by_name=user.get("full_name"),
            reason=reason,
        )
        flash("Permintaan reopen dikirim untuk ditinjau admin.", "success")
    else:
        flash("Permintaan reopen sudah ada atau gagal dibuat.", "warning")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))


@hospitality_bp.route("/admin/reopen/<int:request_id>/update", methods=["POST"])
@role_required("admin")
def handle_reopen_request(request_id: int) -> Response:
    status = request.form.get("status", "").lower()
    note = (request.form.get("note") or "").strip() or None
    return _update_reopen_status(request_id=request_id, status=status, reviewer_note=note)


@hospitality_bp.route("/admin/reopen/<int:assessment_id>/approve", methods=["POST"])
@role_required("admin")
def approve_reopen(assessment_id: int) -> Response:
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    request_id = request.form.get("request_id", type=int)
    if not request_id:
        request_id = get_latest_reopen_request_id(assessment_id)
    if not request_id:
        if wants_json:
            return jsonify({"success": False, "message": "Permintaan reopen tidak ditemukan."}), 404
        flash("Permintaan reopen tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_reopen_requests"))
    note = (request.form.get("reviewer_note") or "").strip() or None
    return _update_reopen_status(request_id=request_id, status="approved", reviewer_note=note)


@hospitality_bp.route("/admin/reopen/<int:assessment_id>/reject", methods=["POST"])
@role_required("admin")
def reject_reopen(assessment_id: int) -> Response:
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    request_id = request.form.get("request_id", type=int)
    if not request_id:
        request_id = get_latest_reopen_request_id(assessment_id)
    if not request_id:
        if wants_json:
            return jsonify({"success": False, "message": "Permintaan reopen tidak ditemukan."}), 404
        flash("Permintaan reopen tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_reopen_requests"))
    note = (request.form.get("reviewer_note") or "").strip() or None
    return _update_reopen_status(request_id=request_id, status="rejected", reviewer_note=note)


def _update_reopen_status(*, request_id: int, status: str, reviewer_note: Optional[str]) -> Response:
    user = current_user()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        req = update_reopen_request_status(
            request_id=request_id,
            status=status,
            reviewer_id=int(user.get("id")),
            reviewer_note=reviewer_note,
        )
        if req:
            assessment = get_assessment(req.get("assessment_id"))
            recipients = set()
            recipients.update(_school_user_ids((assessment or {}).get("school_id")))
            if assessment:
                recipients.add(int(assessment.get("staff_id")))
            create_user_notifications(
                recipient_ids=list(recipients),
                category=HOSPITALITY_NOTIFICATION_CATEGORY,
                title=f"Reopen {status}",
                message=reviewer_note or f"Permintaan reopen {status}.",
                reference_table="hospitality_assessments",
                reference_id=req.get("assessment_id"),
                link=url_for("hospitality.assessment_detail", assessment_id=req.get("assessment_id")),
            )
            notify_reopen_status_update(
                request_id=req.get("id"),
                assessment_id=req.get("assessment_id"),
                school_name=(assessment or {}).get("school_name"),
                period_name=None,
                staff_name=(assessment or {}).get("staff_name"),
                status_label=status,
                actor_name=user.get("full_name"),
                actor_username=user.get("email"),
                reviewer_note=reviewer_note,
            )
            log_activity(
                user_id=int(user.get("id")),
                action=f"reopen_{status}",
                target_type="HOSPITALITY_REOPEN_REQUEST",
                target_id=req.get("id"),
                target_name=(assessment or {}).get("school_name", f"ID {req.get('assessment_id')}"),
                details={"description": f"{'Menyetujui' if status == 'approved' else 'Menolak'} permintaan reopen penilaian {(assessment or {}).get('school_name', '')}", "reviewer_note": reviewer_note, "assessment_id": req.get("assessment_id")},
            )
            flash("Status reopen diperbarui.", "success")
            if wants_json:
                return jsonify(
                    {
                        "success": True,
                        "request_id": req.get("id"),
                        "assessment_id": req.get("assessment_id"),
                        "status": status,
                    }
                )
        else:
            flash("Permintaan tidak ditemukan.", "warning")
            if wants_json:
                return jsonify({"success": False, "message": "Permintaan tidak ditemukan."}), 404
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
        if wants_json:
            return jsonify({"success": False, "message": str(exc)}), 500
    return redirect(url_for("hospitality.admin_reopen_requests"))


@hospitality_bp.route("/sekolah")
@role_required("sekolah")
def school_home() -> Response:
    user = current_user()
    school = _fetch_user_school(user.get("id"))
    if not school:
        flash("Akun belum terhubung ke data sekolah.", "warning")
        return redirect(url_for("portal.sekolah_home"))
    assessments = list_assessments_for_school(school_id=int(school.get("id")))
    return render_template(
        "hospitality/school/list.html",
        school=school,
        assessments=assessments,
    )


@hospitality_bp.route("/preview")
@_hospitality_preview_required
def preview_home() -> Response:
    status_filter = (request.args.get("status") or "").strip().lower() or None
    search = (request.args.get("q") or "").strip() or None
    assessments = list_assessments_for_preview(
        status=status_filter,
        search=search,
        limit=250,
    )
    return render_template(
        "hospitality/preview/list.html",
        assessments=assessments,
        status_filter=status_filter or "",
        search_query=search or "",
    )


@hospitality_bp.route("/preview/<int:assessment_id>")
@_hospitality_preview_required
def preview_detail(assessment_id: int) -> Response:
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    scores = get_assessment_scores(assessment_id)
    components = list_components_with_aspects(active_only=False)
    scores_map = {s.get("aspect_id"): s for s in scores}
    comments = list_comments(assessment_id)
    return render_template(
        "hospitality/detail.html",
        assessment=assessment,
        components=components,
        scores_map=scores_map,
        guestbook_options=[],
        comments=comments,
        latest_reopen_request=None,
        user_role="preview",
        is_staff=False,
        is_school=False,
        preview_read_only=True,
        preview_back_url=url_for("hospitality.preview_home"),
    )


@hospitality_bp.route("/preview/pelayanan")
@_hospitality_preview_required
def preview_guestbook_dashboard() -> Response:
    return _render_preview_guestbook_dashboard(mode="all")


@hospitality_bp.route("/preview/pelayanan/per-sekolah")
@_hospitality_preview_required
def preview_guestbook_dashboard_by_school() -> Response:
    return _render_preview_guestbook_dashboard(mode="school")


def _render_preview_guestbook_dashboard(*, mode: str) -> Response:
    school_scope: Optional[Dict[str, Any]] = None
    scope_school_id: Optional[int] = None
    school_id_arg = request.args.get("school_id", type=int)
    if school_id_arg:
        school_scope = _school_by_id(school_id_arg)
        if school_scope:
            scope_school_id = int(school_scope.get("id"))
        else:
            flash("Sekolah tidak ditemukan.", "warning")

    review_status = (request.args.get("review_status") or "").strip().lower() or None
    transaction_status = (request.args.get("transaction_status") or "").strip().lower() or None
    rating_filter = request.args.get("rating", type=int)
    search = (request.args.get("q") or "").strip() or None
    start_date = _parse_guestbook_date(request.args.get("start"))
    end_date = _parse_guestbook_date(request.args.get("end"))
    page = request.args.get("page", type=int) or 1
    per_page = request.args.get("per_page", type=int) or 25
    per_page = max(5, min(int(per_page or 25), 100))

    use_te = _use_tanggal_edit()
    reviews, total_rows = list_guestbook_reviews(
        school_id=scope_school_id,
        review_status=review_status,
        transaction_status=transaction_status,
        rating=rating_filter,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
        use_tanggal_edit=use_te,
    )
    stats = fetch_guestbook_review_stats(
        school_id=scope_school_id,
        start_date=start_date,
        end_date=end_date,
        use_tanggal_edit=use_te,
    )
    trend = fetch_guestbook_review_trend(days=30, school_id=scope_school_id, use_tanggal_edit=use_te)
    trend_90 = fetch_guestbook_review_trend(days=90, school_id=scope_school_id, use_tanggal_edit=use_te)
    trend_365 = fetch_guestbook_review_trend(days=365, school_id=scope_school_id, use_tanggal_edit=use_te)
    rating_distribution = fetch_guestbook_review_rating_distribution(school_id=scope_school_id)
    top_schools = []
    bottom_schools = []
    if not scope_school_id:
        top_schools = fetch_guestbook_review_top_schools(limit=10)
        bottom_schools = fetch_guestbook_review_bottom_schools(limit=10)

    dashboard_endpoint = (
        "hospitality.preview_guestbook_dashboard_by_school"
        if (mode or "").strip().lower() == "school"
        else "hospitality.preview_guestbook_dashboard"
    )

    filter_params = {key: value for key, value in request.args.items() if value not in ("", None)}
    filter_params.pop("page", None)
    filter_params.pop("per_page", None)
    prev_url = None
    next_url = None
    total_pages = max(1, (total_rows + per_page - 1) // per_page)
    if page > 1:
        prev_url = url_for(dashboard_endpoint, **filter_params, page=page - 1, per_page=per_page)
    if page < total_pages:
        next_url = url_for(dashboard_endpoint, **filter_params, page=page + 1, per_page=per_page)

    school_options = _list_active_schools()
    start_item = ((page - 1) * per_page + 1) if total_rows else 0
    end_item = min(page * per_page, total_rows) if total_rows else 0

    return render_template(
        "hospitality/guestbook/list.html",
        reviews=reviews,
        stats=stats,
        trend=trend,
        trend_90=trend_90,
        trend_365=trend_365,
        rating_distribution=rating_distribution,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        school_scope=school_scope,
        school_options=school_options,
        review_status_filter=review_status or "",
        transaction_status_filter=transaction_status or "",
        rating_filter=rating_filter or "",
        search_query=search or "",
        start_filter=start_date.isoformat() if start_date else "",
        end_filter=end_date.isoformat() if end_date else "",
        per_page=per_page,
        page=page,
        total_pages=total_pages,
        total_rows=total_rows,
        start_item=start_item,
        end_item=end_item,
        prev_url=prev_url,
        next_url=next_url,
        export_url=None,
        is_admin=False,
        can_delete_reviews=False,
        can_export=False,
        allow_school_filter=True,
        show_rankings=not scope_school_id,
        back_url=url_for("hospitality.preview_home"),
        dashboard_endpoint=dashboard_endpoint,
        detail_endpoint="hospitality.preview_guestbook_review_detail",
        assessment_endpoint="hospitality.preview_detail",
        is_preview_mode=True,
        current_preview_mode="school" if dashboard_endpoint.endswith("by_school") else "all",
        all_schools_url=url_for("hospitality.preview_guestbook_dashboard"),
        per_school_endpoint="hospitality.preview_guestbook_dashboard_by_school",
        per_school_url=url_for("hospitality.preview_guestbook_dashboard_by_school"),
        use_tanggal_edit=use_te,
        rankings_url=url_for("hospitality.preview_guestbook_rankings"),
    )


@hospitality_bp.route("/preview/pelayanan/review/<int:review_id>")
@_hospitality_preview_required
def preview_guestbook_review_detail(review_id: int) -> Response:
    review = get_guestbook_review_detail(review_id)
    if not review:
        abort(404)
    school = _school_by_id(int(review.get("school_id") or 0))
    linked_assessment_url = (
        url_for("hospitality.preview_detail", assessment_id=review.get("linked_assessment_id"))
        if review.get("linked_assessment_id")
        else None
    )
    referrer = request.referrer or ""
    dashboard_endpoint = (
        "hospitality.preview_guestbook_dashboard_by_school"
        if "/preview/pelayanan/per-sekolah" in referrer
        else "hospitality.preview_guestbook_dashboard"
    )
    back_url = referrer if referrer.startswith(request.host_url) else url_for("hospitality.preview_guestbook_dashboard")
    return render_template(
        "hospitality/guestbook/detail.html",
        review=review,
        school=school,
        linked_assessment_url=linked_assessment_url,
        back_url=back_url,
        is_admin=False,
        dashboard_endpoint=dashboard_endpoint,
        use_tanggal_edit=_use_tanggal_edit(),
    )


@hospitality_bp.route("/guestbook-reviews")
@role_required("admin", "sekolah")
def guestbook_review_dashboard() -> Response:
    user = current_user()
    role = (user.get("role") or "").strip().lower()
    view_mode = (request.args.get("view") or "all").strip().lower()
    if view_mode not in {"all", "school"}:
        view_mode = "all"
    if role != "admin":
        view_mode = "school" if role == "sekolah" else "all"

    school_scope: Optional[Dict[str, Any]] = None
    scope_school_id: Optional[int] = None
    if role == "sekolah":
        school_scope, scope_school_id = _guestbook_review_scope_for_user(user)
        if not school_scope:
            flash("Akun sekolah belum terhubung ke data sekolah.", "warning")
            return redirect(url_for("hospitality.school_home"))
    else:
        school_id_arg = request.args.get("school_id", type=int)
        if school_id_arg:
            school_scope = _school_by_id(school_id_arg)
            if school_scope:
                scope_school_id = int(school_scope.get("id"))
            else:
                flash("Sekolah tidak ditemukan.", "warning")

    review_status = (request.args.get("review_status") or "").strip().lower() or None
    transaction_status = (request.args.get("transaction_status") or "").strip().lower() or None
    rating_filter = request.args.get("rating", type=int)
    search = (request.args.get("q") or "").strip() or None
    start_date = _parse_guestbook_date(request.args.get("start"))
    end_date = _parse_guestbook_date(request.args.get("end"))
    page = request.args.get("page", type=int) or 1
    per_page = request.args.get("per_page", type=int) or 25
    per_page = max(5, min(int(per_page or 25), 100))

    should_require_school_pick = role == "admin" and view_mode == "school" and not scope_school_id
    if should_require_school_pick:
        reviews, total_rows = [], 0
        stats = {
            "total_reviews": 0,
            "completed_reviews": 0,
            "pending_reviews": 0,
            "completion_rate": 0.0,
            "avg_rating": 0.0,
            "created_today": 0,
            "completed_today": 0,
            "linked_reviews": 0,
            "linked_rate": 0.0,
        }
        trend = []
        trend_90 = []
        trend_365 = []
        rating_distribution = []
    else:
        use_te = _use_tanggal_edit()
        reviews, total_rows = list_guestbook_reviews(
            school_id=scope_school_id,
            review_status=review_status,
            transaction_status=transaction_status,
            rating=rating_filter,
            search=search,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
            use_tanggal_edit=use_te,
        )
        stats = fetch_guestbook_review_stats(
            school_id=scope_school_id,
            start_date=start_date,
            end_date=end_date,
            use_tanggal_edit=use_te,
        )
        trend = fetch_guestbook_review_trend(days=30, school_id=scope_school_id, use_tanggal_edit=use_te)
        trend_90 = fetch_guestbook_review_trend(days=90, school_id=scope_school_id, use_tanggal_edit=use_te)
        trend_365 = fetch_guestbook_review_trend(days=365, school_id=scope_school_id, use_tanggal_edit=use_te)
        rating_distribution = fetch_guestbook_review_rating_distribution(school_id=scope_school_id)
    top_schools = []
    bottom_schools = []
    if role == "admin" and view_mode == "all" and not scope_school_id:
        top_schools = fetch_guestbook_review_top_schools(limit=10)
        bottom_schools = fetch_guestbook_review_bottom_schools(limit=10)

    filter_params = {key: value for key, value in request.args.items() if value not in ("", None)}
    filter_params.pop("page", None)
    filter_params.pop("per_page", None)
    prev_url = None
    next_url = None
    total_pages = max(1, (total_rows + per_page - 1) // per_page)
    if page > 1:
        prev_url = url_for("hospitality.guestbook_review_dashboard", **filter_params, page=page - 1, per_page=per_page)
    if page < total_pages:
        next_url = url_for("hospitality.guestbook_review_dashboard", **filter_params, page=page + 1, per_page=per_page)

    school_options = _list_active_schools() if role == "admin" else []

    start_item = ((page - 1) * per_page + 1) if total_rows else 0
    end_item = min(page * per_page, total_rows) if total_rows else 0

    return render_template(
        "hospitality/guestbook/list.html",
        reviews=reviews,
        stats=stats,
        trend=trend,
        trend_90=trend_90,
        trend_365=trend_365,
        rating_distribution=rating_distribution,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        school_scope=school_scope,
        school_options=school_options,
        review_status_filter=review_status or "",
        transaction_status_filter=transaction_status or "",
        rating_filter=rating_filter or "",
        search_query=search or "",
        start_filter=start_date.isoformat() if start_date else "",
        end_filter=end_date.isoformat() if end_date else "",
        per_page=per_page,
        page=page,
        total_pages=total_pages,
        total_rows=total_rows,
        start_item=start_item,
        end_item=end_item,
        prev_url=prev_url,
        next_url=next_url,
        export_url=url_for("hospitality.guestbook_review_export", **filter_params),
        is_admin=role == "admin",
        can_delete_reviews=role == "admin",
        can_export=True,
        allow_school_filter=role == "admin",
        show_rankings=(role == "admin" and view_mode == "all" and not scope_school_id),
        back_url=url_for("hospitality.admin_home") if role == "admin" else url_for("hospitality.school_home"),
        dashboard_endpoint="hospitality.guestbook_review_dashboard",
        detail_endpoint="hospitality.guestbook_review_detail",
        assessment_endpoint="hospitality.assessment_detail",
        is_preview_mode=False,
        current_preview_mode=view_mode,
        all_schools_url=url_for("hospitality.guestbook_review_dashboard", view="all"),
        per_school_url=url_for("hospitality.guestbook_review_dashboard", view="school"),
        per_school_endpoint="hospitality.guestbook_review_dashboard",
        require_school_pick=should_require_school_pick,
        use_tanggal_edit=_use_tanggal_edit(),
        rankings_url=url_for("hospitality.guestbook_review_rankings"),
    )


@hospitality_bp.route("/guestbook-reviews/<int:review_id>")
@role_required("admin", "sekolah")
def guestbook_review_detail(review_id: int) -> Response:
    user = current_user()
    role = (user.get("role") or "").strip().lower()
    review = get_guestbook_review_detail(review_id)
    if not review:
        abort(404)

    if role == "sekolah":
        school_scope, scope_school_id = _guestbook_review_scope_for_user(user)
        if not school_scope or int(scope_school_id or 0) != int(review.get("school_id") or 0):
            abort(403)

    school = _school_by_id(int(review.get("school_id") or 0))
    linked_assessment_url = (
        url_for("hospitality.assessment_detail", assessment_id=review.get("linked_assessment_id"))
        if review.get("linked_assessment_id")
        else None
    )
    referrer = request.referrer or ""
    back_url = referrer if referrer.startswith(request.host_url) else url_for("hospitality.guestbook_review_dashboard")
    return render_template(
        "hospitality/guestbook/detail.html",
        review=review,
        school=school,
        linked_assessment_url=linked_assessment_url,
        back_url=back_url,
        is_admin=role == "admin",
        dashboard_endpoint="hospitality.guestbook_review_dashboard",
        use_tanggal_edit=_use_tanggal_edit(),
    )


@hospitality_bp.route("/guestbook-reviews/export")
@role_required("admin", "sekolah")
def guestbook_review_export() -> Response:
    user = current_user()
    role = (user.get("role") or "").strip().lower()

    school_scope_id: Optional[int] = None
    if role == "sekolah":
        school_scope, school_scope_id = _guestbook_review_scope_for_user(user)
        if not school_scope:
            flash("Akun sekolah belum terhubung ke data sekolah.", "warning")
            return redirect(url_for("hospitality.school_home"))
    else:
        school_id_arg = request.args.get("school_id", type=int)
        if school_id_arg:
            school_scope = _school_by_id(school_id_arg)
            if school_scope:
                school_scope_id = int(school_scope.get("id"))

    review_status = (request.args.get("review_status") or "").strip().lower() or None
    transaction_status = (request.args.get("transaction_status") or "").strip().lower() or None
    rating_filter = request.args.get("rating", type=int)
    search = (request.args.get("q") or "").strip() or None
    start_date = _parse_guestbook_date(request.args.get("start"))
    end_date = _parse_guestbook_date(request.args.get("end"))

    rows = fetch_guestbook_reviews_export(
        school_id=school_scope_id,
        review_status=review_status,
        transaction_status=transaction_status,
        rating=rating_filter,
        search=search,
        start_date=start_date,
        end_date=end_date,
        use_tanggal_edit=_use_tanggal_edit(),
    )

    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "review_id",
            "transaction_id",
            "school_name",
            "npsn",
            "jenjang",
            "guest_display",
            "guest_count",
            "review_status",
            "rating",
            "comment",
            "transaction_status",
            "visit_at",
            "completed_at",
            "activity_at",
            "linked_assessment_id",
            "linked_assessment_status",
            "linked_assessment_staff_name",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("review_id"),
                row.get("transaction_id"),
                row.get("school_name"),
                row.get("npsn"),
                row.get("jenjang"),
                row.get("guest_display"),
                row.get("guest_count"),
                row.get("review_status"),
                row.get("rating"),
                row.get("comment"),
                row.get("transaction_status"),
                row.get("visit_at"),
                row.get("completed_at"),
                row.get("activity_at"),
                row.get("linked_assessment_id"),
                row.get("linked_assessment_status"),
                row.get("linked_assessment_staff_name"),
            ]
        )

    response = Response(output.getvalue(), mimetype="text/csv")
    filename = f"hospitality_guestbook_reviews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response


def _list_jenjang_options() -> List[str]:
    """Return distinct jenjang values from portal_schools."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT jenjang
            FROM portal_schools
            WHERE active = TRUE AND jenjang IS NOT NULL AND jenjang != ''
            ORDER BY jenjang ASC
            """
        )
        return [row["jenjang"] for row in cur.fetchall()]


def _list_kecamatan_options() -> List[str]:
    """Return distinct kecamatan values from portal_schools."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT kec.name
            FROM portal_schools s
            JOIN portal_kelurahan kel ON s.kelurahan_id = kel.id
            JOIN portal_kecamatan kec ON kel.kecamatan_id = kec.id
            WHERE s.active = TRUE AND kec.name IS NOT NULL AND kec.name != ''
            ORDER BY kec.name ASC
            """
        )
        return [row["name"] for row in cur.fetchall()]


@hospitality_bp.route("/guestbook-reviews/rankings")
@role_required("admin")
def guestbook_review_rankings() -> Response:
    return _render_guestbook_rankings(
        is_preview=False,
        back_url=url_for("hospitality.guestbook_review_dashboard", view="all"),
        detail_endpoint="hospitality.guestbook_review_dashboard",
    )


@hospitality_bp.route("/preview/pelayanan/rankings")
@_hospitality_preview_required
def preview_guestbook_rankings() -> Response:
    return _render_guestbook_rankings(
        is_preview=True,
        back_url=url_for("hospitality.preview_guestbook_dashboard"),
        detail_endpoint="hospitality.preview_guestbook_dashboard_by_school",
    )


def _render_guestbook_rankings(
    *,
    is_preview: bool,
    back_url: str,
    detail_endpoint: str,
) -> Response:
    search = (request.args.get("q") or "").strip() or None
    jenjang = (request.args.get("jenjang") or "").strip() or None
    kecamatan = (request.args.get("kecamatan") or "").strip() or None
    school_status = (request.args.get("school_status") or "").strip() or None
    sort_by = (request.args.get("sort") or "avg_rating").strip().lower()
    sort_dir = (request.args.get("dir") or "desc").strip().lower()
    page = request.args.get("page", type=int) or 1
    per_page = request.args.get("per_page", type=int) or 50
    per_page = max(5, min(int(per_page or 50), 200))

    schools, total = fetch_guestbook_review_school_rankings(
        search=search,
        jenjang=jenjang,
        kecamatan=kecamatan,
        school_status=school_status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page,
    )

    total_pages = max(1, (total + per_page - 1) // per_page)
    start_item = ((page - 1) * per_page + 1) if total else 0
    end_item = min(page * per_page, total) if total else 0

    filter_params = {k: v for k, v in request.args.items() if v not in ("", None)}
    filter_params.pop("page", None)
    filter_params.pop("per_page", None)

    rankings_endpoint = (
        "hospitality.preview_guestbook_rankings" if is_preview
        else "hospitality.guestbook_review_rankings"
    )

    prev_url = (
        url_for(rankings_endpoint, **filter_params, page=page - 1, per_page=per_page)
        if page > 1 else None
    )
    next_url = (
        url_for(rankings_endpoint, **filter_params, page=page + 1, per_page=per_page)
        if page < total_pages else None
    )

    jenjang_options = _list_jenjang_options()
    kecamatan_options = _list_kecamatan_options()

    return render_template(
        "hospitality/guestbook/rankings.html",
        schools=schools,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        start_item=start_item,
        end_item=end_item,
        prev_url=prev_url,
        next_url=next_url,
        search_query=search or "",
        jenjang_filter=jenjang or "",
        kecamatan_filter=kecamatan or "",
        school_status_filter=school_status or "",
        sort_by=sort_by,
        sort_dir=sort_dir,
        jenjang_options=jenjang_options,
        kecamatan_options=kecamatan_options,
        back_url=back_url,
        is_preview=is_preview,
        rankings_endpoint=rankings_endpoint,
        detail_endpoint=detail_endpoint,
    )


@hospitality_bp.route("/admin/guestbook-reviews/<int:review_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_guestbook_review(review_id: int) -> Response:
    user = current_user()
    try:
        deleted = delete_guestbook_review(review_id=review_id, deleted_by=int(user.get("id")))
        if deleted:
            log_activity(
                user_id=int(user.get("id")),
                action="delete",
                target_type="GUESTBOOK_REVIEW",
                target_id=review_id,
                target_name=f"Review Pelayanan #{review_id}",
                details={"description": f"Menghapus review pelayanan (ID: {review_id})"},
            )
            flash("Review pelayanan berhasil dihapus.", "success")
        else:
            flash("Review pelayanan tidak ditemukan.", "warning")
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
    fallback = url_for("hospitality.guestbook_review_dashboard")
    referrer = request.referrer or ""
    return redirect(referrer if referrer.startswith(request.host_url) else fallback)


@hospitality_bp.route("/admin")
@role_required("admin")
def admin_home() -> Response:
    status = (request.args.get("status") or "").strip().lower() or None
    trend_range = (request.args.get("trend_range") or "30d").strip().lower()
    trend_days_map = {
        "30d": 30,
        "60d": 60,
        "1y": 365,
        "all": None,
    }
    if trend_range not in trend_days_map:
        trend_range = "30d"
    reopen_requests = list_reopen_requests(status=status, limit=200)
    from .queries import (
        fetch_stats,
        fetch_daily_trend,
        fetch_top_schools,
        fetch_bottom_schools,
        fetch_recent_assessments,
        fetch_linked_photos,
        fetch_component_averages,
    )
    stats = fetch_stats()
    trend = fetch_daily_trend(days=trend_days_map[trend_range])
    top_schools = fetch_top_schools(limit=10)
    bottom_schools = fetch_bottom_schools(limit=10)
    recent = fetch_recent_assessments(limit=20)
    linked_photos = fetch_linked_photos(limit=12)
    activity_logs = fetch_activity_logs(limit=20)
    return render_template(
        "hospitality/admin/list.html",
        reopen_requests=reopen_requests,
        status_filter=status or "",
        stats=stats,
        trend=trend,
        trend_range=trend_range,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        recent_assessments=recent,
        linked_photos=linked_photos,
        activity_logs=activity_logs,
        component_averages=fetch_component_averages(),
    )


@hospitality_bp.route("/admin/api/rankings")
@role_required("admin")
def admin_api_rankings() -> Response:
    """API endpoint untuk memuat tambahan data perankingan sekolah."""
    from .queries import fetch_bottom_schools, fetch_top_schools

    type_ = (request.args.get("type") or "best").strip().lower()
    if type_ not in {"best", "worst"}:
        type_ = "best"

    limit = request.args.get("limit", 10, type=int)
    offset = request.args.get("offset", 0, type=int)
    safe_limit = max(1, min(int(limit or 10), 50))
    safe_offset = max(0, int(offset or 0))

    if type_ == "worst":
        rows = fetch_bottom_schools(limit=safe_limit, offset=safe_offset)
    else:
        rows = fetch_top_schools(limit=safe_limit, offset=safe_offset)

    payload = []
    for row in rows:
        payload.append(
            {
                "school_id": row.get("school_id"),
                "school_name": row.get("school_name"),
                "jenjang": row.get("jenjang"),
                "assessment_count": int(row.get("assessment_count") or 0),
                "avg_pct": float(row.get("avg_pct") or 0),
            }
        )
    return jsonify(payload)


@hospitality_bp.route("/admin/all-assessments")
@role_required("admin")
def admin_all_assessments() -> Response:
    """Full paginated list of all hospitality assessments."""
    search = (request.args.get("q") or "").strip() or None
    status = (request.args.get("status") or "").strip().lower() or None
    jenjang = (request.args.get("jenjang") or "").strip() or None
    kecamatan = (request.args.get("kecamatan") or "").strip() or None
    school_status = (request.args.get("school_status") or "").strip() or None
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = max(10, min(per_page, 100))

    assessments, total = fetch_all_assessed_schools(
        search=search,
        status=status,
        jenjang=jenjang,
        kecamatan=kecamatan,
        school_status=school_status,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_item = ((page - 1) * per_page + 1) if total else 0
    end_item = min(page * per_page, total) if total else 0

    filter_params = {key: value for key, value in request.args.items() if value not in ("", None)}
    filter_params.pop("page", None)
    prev_url = url_for("hospitality.admin_all_assessments", **filter_params, page=page - 1) if page > 1 else None
    next_url = url_for("hospitality.admin_all_assessments", **filter_params, page=page + 1) if page < total_pages else None

    jenjang_options = _list_jenjang_options()
    kecamatan_options = _list_kecamatan_options()

    return render_template(
        "hospitality/admin/all_assessments.html",
        assessments=assessments,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        start_item=start_item,
        end_item=end_item,
        prev_url=prev_url,
        next_url=next_url,
        search_query=search or "",
        status_filter=status or "",
        jenjang_filter=jenjang or "",
        kecamatan_filter=kecamatan or "",
        school_status_filter=school_status or "",
        jenjang_options=jenjang_options,
        kecamatan_options=kecamatan_options,
    )


@hospitality_bp.route("/admin/activity-logs")
@role_required("admin")
def admin_activity_logs() -> Response:
    page = request.args.get("page", 1, type=int)
    per_page = 50
    activity_logs = fetch_activity_logs(limit=per_page, offset=(page - 1) * per_page)
    return render_template(
        "hospitality/admin/activity_logs.html",

        activity_logs=activity_logs,
        page=page,
        per_page=per_page,
    )


@hospitality_bp.route("/admin/menilai")
@role_required("admin")
def admin_assess_home() -> Response:
    """Admin assessment list – same UX as staff_home but for admin."""
    user = current_user()
    status_filter = (request.args.get("status") or "").strip().lower() or None
    search = (request.args.get("q") or "").strip() or None
    assessments = list_assessments_for_staff(
        staff_id=int(user.get("id")),
        status=status_filter,
        search=search,
    )
    draft_assessment = get_latest_draft_assessment_for_staff(staff_id=int(user.get("id")))
    if draft_assessment and (not status_filter or status_filter == "draft"):
        draft_id = draft_assessment.get("id")
        assessments = [item for item in assessments if item.get("id") != draft_id]
        assessments = [draft_assessment] + assessments
    return render_template(
        "hospitality/staff/list.html",
        assessments=assessments,
        draft_assessment=draft_assessment,
        score_max=HOSPITALITY_SCORE_MAX,
        status_filter=status_filter or "",
        search_query=search or "",
        admin_assess_mode=True,
    )


@hospitality_bp.route("/admin/menilai/assess/<int:school_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_assess(school_id: int) -> Response:
    """Admin assess a school – same UX as staff_assess."""
    user = current_user()
    components = list_components_with_aspects(active_only=True)
    school = None
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, npsn, jenjang FROM portal_schools WHERE id = %s",
            (school_id,),
        )
        school = cur.fetchone()
    if not school:
        abort(404)

    assessment = get_draft_assessment(school_id=school_id, staff_id=int(user.get("id")))
    if not assessment:
        assessment = get_latest_assessment_for_staff_school(school_id=school_id, staff_id=int(user.get("id")))
    if not assessment:
        assessment = create_assessment(
            school_id=school_id,
            staff_id=int(user.get("id")),
            score_scale_max=HOSPITALITY_SCORE_MAX,
            note_text=None,
        )

    if request.method == "POST":
        note_text = (request.form.get("note") or "").strip() or None
        status_action = (request.form.get("action") or "draft").strip().lower()
        try:
            scores_payload: List[Dict[str, Any]] = []
            for comp in components:
                for aspect in comp.get("aspects") or []:
                    field = f"score_{aspect['id']}"
                    raw = request.form.get(field)
                    if raw is None:
                        continue
                    try:
                        score_val = int(raw)
                    except (TypeError, ValueError):
                        continue
                    scores_payload.append(
                        {
                            "component_id": comp["id"],
                            "aspect_id": aspect["id"],
                            "score": score_val,
                            "note": None,
                        }
                    )
            upsert_scores(assessment_id=int(assessment["id"]), scores=scores_payload)
            if status_action == "submit":
                submit_assessment(
                    assessment_id=int(assessment["id"]),
                    note_text=note_text,
                    score_scale_max=HOSPITALITY_SCORE_MAX,
                )
                flash("Penilaian tersimpan dan dikirim.", "success")
                return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment["id"]))
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    UPDATE hospitality_assessments
                    SET note_text = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (note_text, int(assessment["id"])),
                )
            flash("Draft penilaian disimpan.", "success")
            return redirect(url_for("hospitality.admin_assess", school_id=school_id))
        except Exception as exc:  # pragma: no cover
            flash(str(exc), "danger")

    assessment_scores = get_assessment_scores(int(assessment["id"])) if assessment else []
    scores_map = {s.get("aspect_id"): s.get("score") for s in assessment_scores}
    notes_by_component = {s.get("component_id"): s.get("note") for s in assessment_scores if s.get("note")}

    return render_template(
        "hospitality/staff/assess.html",
        school=school,
        components=components,
        assessment=assessment,
        assessment_status=assessment.get("status") if assessment else "draft",
        scores_map=scores_map,
        notes_by_component=notes_by_component,
        score_scale=list(range(1, HOSPITALITY_SCORE_MAX + 1)),
        admin_assess_mode=True,
    )


@hospitality_bp.route("/admin/menilai/assess/<int:school_id>/score", methods=["POST"])
@role_required("admin")
def admin_assess_save_score(school_id: int) -> Response:
    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
        aspect_id = int(data.get("aspect_id"))
        component_id = int(data.get("component_id"))
        score = int(data.get("score"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data tidak valid"}), 400
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404
    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim."}), 400
    try:
        upsert_scores(
            assessment_id=assessment_id,
            scores=[{"component_id": component_id, "aspect_id": aspect_id, "score": score, "note": None}],
        )
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@hospitality_bp.route("/admin/menilai/assess/<int:school_id>/note", methods=["POST"])
@role_required("admin")
def admin_assess_save_note(school_id: int) -> Response:
    data = request.get_json(silent=True) or {}
    try:
        assessment_id = int(data.get("assessment_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Data tidak valid"}), 400
    note = (data.get("note") or "").strip() or None
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        return jsonify({"success": False, "message": "Assessment tidak ditemukan"}), 404
    if assessment.get("status") != "draft":
        return jsonify({"success": False, "message": "Penilaian sudah dikirim."}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE hospitality_assessments SET note_text = %s, updated_at = NOW() WHERE id = %s",
            (note, assessment_id),
        )
    return jsonify({"success": True})


@hospitality_bp.route("/admin/menilai/assess/<int:school_id>/draft", methods=["POST"])
@role_required("admin")
def admin_assess_save_draft(school_id: int) -> Response:
    assessment_id = request.form.get("assessment_id", type=int)
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("hospitality.admin_assess", school_id=school_id))
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        flash("Assessment tidak ditemukan.", "danger")
        return redirect(url_for("hospitality.admin_assess", school_id=school_id))
    if assessment.get("status") != "draft":
        flash("Penilaian sudah dikirim.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))
    flash("Draft penilaian disimpan.", "success")
    return redirect(url_for("hospitality.admin_assess", school_id=school_id))


@hospitality_bp.route("/admin/menilai/assess/<int:school_id>/submit", methods=["POST"])
@role_required("admin")
def admin_assess_submit(school_id: int) -> Response:
    assessment_id = request.form.get("assessment_id", type=int)
    if not assessment_id:
        flash("Assessment ID tidak valid.", "danger")
        return redirect(url_for("hospitality.admin_assess", school_id=school_id))
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("school_id")) != school_id:
        flash("Assessment tidak ditemukan.", "danger")
        return redirect(url_for("hospitality.admin_assess", school_id=school_id))
    if assessment.get("status") != "draft":
        flash("Penilaian sudah dikirim.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))
    required_aspects = _hospitality_required_aspect_count()
    scored_aspects = _hospitality_scored_aspect_count(assessment_id)
    if required_aspects > 0 and scored_aspects < required_aspects:
        flash("Semua aspek harus dinilai sebelum submit.", "warning")
        return redirect(url_for("hospitality.admin_assess", school_id=school_id))
    submit_assessment(
        assessment_id=assessment_id,
        note_text=assessment.get("note_text"),
        score_scale_max=HOSPITALITY_SCORE_MAX,
    )
    flash("Penilaian tersimpan dan dikirim.", "success")
    return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))


@hospitality_bp.route("/admin/menilai/draft/<int:assessment_id>/delete", methods=["POST"])
@role_required("admin")
def admin_assess_delete_draft(assessment_id: int) -> Response:
    user = current_user()
    assessment = get_assessment(assessment_id)
    if not assessment or int(assessment.get("staff_id") or 0) != int(user.get("id")):
        return jsonify({"success": False, "message": "Penilaian tidak ditemukan."}), 404
    if (assessment.get("status") or "").lower() != "draft":
        return jsonify({"success": False, "message": "Hanya draft yang dapat dihapus."}), 400
    try:
        delete_draft_assessment(assessment_id=assessment_id)
    except ValueError as exc:  # pragma: no cover
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True})


@hospitality_bp.route("/admin/reopen-requests")
@role_required("admin")
def admin_reopen_requests() -> Response:
    status = (request.args.get("status") or "").strip().lower() or None
    requests = list_reopen_requests(status=status, limit=500)
    return render_template(
        "hospitality/admin/reopen_requests.html",
        reopen_requests=requests,
        status_filter=status or "",
    )


@hospitality_bp.route("/admin/export")
@role_required("admin")
def admin_export_csv() -> Response:
    """Export hospitality assessments with scores to CSV."""
    import csv
    from io import StringIO

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id,
                a.created_at,
                a.submitted_at,
                a.verified_at,
                a.status,
                a.school_id,
                s.name AS school_name,
                s.npsn,
                s.jenjang,
                a.staff_id,
                u.full_name AS staff_name,
                g.transaction_id AS guestbook_transaction_id
            FROM hospitality_assessments a
            JOIN portal_schools s ON s.id = a.school_id
            LEFT JOIN dashboard_users u ON u.id = a.staff_id
            LEFT JOIN hospitality_assessment_guestbook_links g ON g.assessment_id = a.id
            ORDER BY a.created_at DESC
            """
        )
        assessments = [dict(row) for row in cur.fetchall()]

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "assessment_id",
            "created_at",
            "submitted_at",
            "verified_at",
            "status",
            "school_id",
            "school_name",
            "npsn",
            "jenjang",
            "staff_id",
            "staff_name",
            "guestbook_transaction_id",
        ]
    )
    for row in assessments:
        writer.writerow(
            [
                row.get("id"),
                row.get("created_at"),
                row.get("submitted_at"),
                row.get("verified_at"),
                row.get("status"),
                row.get("school_id"),
                row.get("school_name"),
                row.get("npsn"),
                row.get("jenjang"),
                row.get("staff_id"),
                row.get("staff_name"),
                row.get("guestbook_transaction_id"),
            ]
        )

    csv_data = output.getvalue()
    response = Response(csv_data, mimetype="text/csv")
    filename = f"hospitality_assessments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response


@hospitality_bp.route("/admin/setup", methods=["GET"])
@role_required("admin")
def admin_setup() -> Response:
    components = list_components_with_aspects(active_only=False)
    activity_logs = fetch_activity_logs(
        limit=50,
        target_types=["HOSPITALITY_COMPONENT", "HOSPITALITY_ASPECT"]
    )
    return render_template(
        "hospitality/admin/setup.html",
        components=components,
        activity_logs=activity_logs,
    )


@hospitality_bp.route("/admin/preview-access", methods=["GET", "POST"])
@role_required("admin")
def admin_preview_access() -> Response:
    user = current_user()
    if request.method == "POST":
        target_user_id = request.form.get("user_id", type=int)
        if not target_user_id:
            flash("Pilih user terlebih dahulu.", "warning")
            return redirect(url_for("hospitality.admin_preview_access"))
        try:
            grant_hospitality_preview_access(user_id=target_user_id, granted_by=int(user.get("id")))
            log_activity(
                user_id=int(user.get("id")),
                action="grant_preview_access",
                target_type="HOSPITALITY_PREVIEW",
                target_id=target_user_id,
                target_name=f"User ID {target_user_id}",
                details={"description": f"Memberikan akses preview hospitality ke User ID {target_user_id}"},
            )
            flash("Akses preview hospitality diberikan.", "success")
        except Exception as exc:  # pragma: no cover
            flash(str(exc), "danger")
        return redirect(url_for("hospitality.admin_preview_access"))

    search = (request.args.get("q") or "").strip() or None
    granted_users = list_hospitality_preview_access_users(search=search, limit=500)
    candidates = list_hospitality_preview_candidates(search=search, limit=100)
    return render_template(
        "hospitality/admin/preview_access.html",
        granted_users=granted_users,
        candidates=candidates,
        search_query=search or "",
    )


@hospitality_bp.route("/admin/preview-access/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def admin_preview_access_delete(user_id: int) -> Response:
    try:
        revoked = revoke_hospitality_preview_access(user_id=user_id)
        if revoked:
            log_activity(
                user_id=int(current_user().get("id")),
                action="revoke_preview_access",
                target_type="HOSPITALITY_PREVIEW",
                target_id=user_id,
                target_name=f"User ID {user_id}",
                details={"description": f"Mencabut akses preview hospitality dari User ID {user_id}"},
            )
            flash("Akses preview hospitality dicabut.", "success")
        else:
            flash("Akses preview tidak ditemukan.", "warning")
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_preview_access"))


@hospitality_bp.route("/admin/setup/component", methods=["POST"])
@role_required("admin")
def admin_create_component() -> Response:
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    if not name:
        flash("Nama komponen wajib diisi.", "warning")
        return redirect(url_for("hospitality.admin_setup"))
    try:
        comp = create_component(name=name, description=description, sort_order=0, is_required=True, active=True)
        log_activity(
            user_id=int(current_user().get("id")),
            action="create",
            target_type="HOSPITALITY_COMPONENT",
            target_id=comp.get("id"),
            target_name=name,
            details={"description": f"Membuat komponen baru: {name}", "comp_description": description},
        )
        flash("Komponen ditambahkan.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>", methods=["POST"])
@role_required("admin")
def admin_update_component(component_id: int) -> Response:
    comp = get_component(component_id)
    if not comp:
        flash("Komponen tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_setup"))
    name = (request.form.get("name") or comp.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    active = request.form.get("active") == "on"
    sort_order = request.form.get("sort_order", type=int) or comp.get("sort_order") or 0
    is_required = request.form.get("is_required") == "on"
    try:
        update_component(
            component_id=component_id,
            name=name,
            description=description,
            sort_order=sort_order,
            is_required=is_required,
            active=active,
        )
        log_activity(
            user_id=int(current_user().get("id")),
            action="update",
            target_type="HOSPITALITY_COMPONENT",
            target_id=component_id,
            target_name=name,
            details={"description": f"Memperbarui komponen: {name} (Aktif: {'Ya' if active else 'Tidak'}, Wajib: {'Ya' if is_required else 'Tidak'})", "active": active, "is_required": is_required},
        )
        flash("Komponen diperbarui.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_component(component_id: int) -> Response:
    try:
        comp = get_component(component_id)
        if delete_component(component_id):
            comp_name = comp.get("name") if comp else f"ID {component_id}"
            log_activity(
                user_id=int(current_user().get("id")),
                action="delete",
                target_type="HOSPITALITY_COMPONENT",
                target_id=component_id,
                target_name=comp_name,
                details={"description": f"Menghapus komponen: {comp_name}"},
            )
            flash("Komponen dihapus/nonaktif.", "success")
        else:
            flash("Komponen tidak ditemukan.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/toggle-active", methods=["POST"])
@role_required("admin")
def admin_toggle_component_active(component_id: int) -> Response:
    if toggle_component_active(component_id):
        comp = get_component(component_id)
        comp_name = comp.get("name") if comp else f"ID {component_id}"
        new_active = comp.get("active") if comp else None
        log_activity(
            user_id=int(current_user().get("id")),
            action="toggle_active",
            target_type="HOSPITALITY_COMPONENT",
            target_id=component_id,
            target_name=comp_name,
            details={"description": f"Mengubah status komponen {comp_name} menjadi {'Aktif' if new_active else 'Nonaktif'}", "active": new_active},
        )
        flash("Status komponen diperbarui.", "success")
    else:
        flash("Komponen tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/toggle-required", methods=["POST"])
@role_required("admin")
def admin_toggle_component_required(component_id: int) -> Response:
    if toggle_component_required(component_id):
        comp = get_component(component_id)
        comp_name = comp.get("name") if comp else f"ID {component_id}"
        new_required = comp.get("is_required") if comp else None
        log_activity(
            user_id=int(current_user().get("id")),
            action="toggle_required",
            target_type="HOSPITALITY_COMPONENT",
            target_id=component_id,
            target_name=comp_name,
            details={"description": f"Mengubah status wajib komponen {comp_name} menjadi {'Wajib' if new_required else 'Opsional'}", "is_required": new_required},
        )
        flash("Status wajib komponen diperbarui.", "success")
    else:
        flash("Komponen tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/components/reorder", methods=["POST"])
@role_required("admin")
def admin_reorder_components() -> Response:
    data = request.get_json(silent=True) or {}
    order_ids = data.get("component_ids") or []
    try:
        ids = [int(i) for i in order_ids]
        reorder_components(ids)
        log_activity(
            user_id=int(current_user().get("id")),
            action="reorder",
            target_type="HOSPITALITY_COMPONENT",
            target_id=None,
            target_name="Komponen",
            details={"description": f"Mengubah urutan {len(ids)} komponen", "component_ids": ids},
        )
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@hospitality_bp.route("/admin/setup/aspect", methods=["POST"])
@role_required("admin")
def admin_create_aspect() -> Response:
    component_id = request.form.get("component_id", type=int)
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    sort_order = request.form.get("sort_order", type=int) or 0
    is_required = request.form.get("is_required", "on") == "on"
    if not component_id or not name:
        flash("Komponen dan nama aspek wajib diisi.", "warning")
        return redirect(url_for("hospitality.admin_setup"))
    try:
        asp = create_hosp_aspect(
            component_id=component_id,
            name=name,
            description=description,
            sort_order=sort_order,
            is_required=is_required,
            active=True,
        )
        comp_obj = get_component(component_id)
        comp_label = comp_obj.get("name") if comp_obj else f"ID {component_id}"
        log_activity(
            user_id=int(current_user().get("id")),
            action="create",
            target_type="HOSPITALITY_ASPECT",
            target_id=asp.get("id") if asp else None,
            target_name=name,
            details={"description": f"Membuat aspek baru: {name} pada komponen {comp_label}", "component_id": component_id, "component_name": comp_label},
        )
        flash("Aspek ditambahkan.", "success")
        if request.is_json:
            component = get_component(component_id)
            return jsonify({
                "success": True,
                "component_id": component_id,
                "aspects": list_components_with_aspects(active_only=False),
                "component_name": component.get("name") if component else None,
            })
    except Exception as exc:
        if request.is_json:
            return jsonify({"success": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspects/batch", methods=["POST"])
@role_required("admin")
def admin_create_aspects_batch() -> Response:
    data = request.get_json(silent=True) or {}
    aspects = data.get("aspects", [])
    is_required_default = bool(data.get("is_required", True))

    if not aspects:
        return jsonify({"success": False, "error": "Tidak ada aspek yang dikirim"}), 400

    created_count = 0
    errors: list[str] = []
    touched_components: set[int] = set()

    for item in aspects:
        component_id = item.get("componentId")
        name = (item.get("name") or "").strip()
        is_required = bool(item.get("is_required", is_required_default))

        if not component_id or not name:
            errors.append("Missing component_id or name for aspect")
            continue

        try:
            cid = int(component_id)
            create_hosp_aspect(
                component_id=cid,
                name=name,
                description=None,
                sort_order=0,
                is_required=is_required,
                active=True,
            )
            created_count += 1
            touched_components.add(cid)
        except Exception as exc:
            errors.append(f"Error creating '{name}': {exc}")

    if created_count > 0:
        log_activity(
            user_id=int(current_user().get("id")),
            action="batch_create",
            target_type="HOSPITALITY_ASPECT",
            target_id=None,
            target_name=f"{created_count} Aspek Baru",
            details={"description": f"Membuat {created_count} aspek sekaligus", "components": list(touched_components)},
        )

    if request.is_json:
        return jsonify({
            "success": created_count > 0,
            "created": created_count,
            "errors": errors,
            "components": list_components_with_aspects(active_only=False),
            "touched_components": list(touched_components),
        })

    if created_count > 0:
        flash(f"{created_count} aspek berhasil ditambahkan.", "success")
    if errors:
        flash("; ".join(errors), "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>", methods=["POST"])
@role_required("admin")
def admin_update_aspect(aspect_id: int) -> Response:
    aspect = get_hosp_aspect(aspect_id)
    if not aspect:
        flash("Aspek tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_setup"))
    name = (request.form.get("name") or aspect.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    sort_order = request.form.get("sort_order", type=int) or aspect.get("sort_order") or 0
    is_required = request.form.get("is_required", "on") == "on"
    active = request.form.get("active") == "on"
    try:
        update_hosp_aspect(
            aspect_id=aspect_id,
            name=name,
            description=description,
            sort_order=sort_order,
            is_required=is_required,
            active=active,
        )
        log_activity(
            user_id=int(current_user().get("id")),
            action="update",
            target_type="HOSPITALITY_ASPECT",
            target_id=aspect_id,
            target_name=name,
            details={"description": f"Memperbarui aspek: {name} (Aktif: {'Ya' if active else 'Tidak'}, Wajib: {'Ya' if is_required else 'Tidak'})", "active": active, "is_required": is_required},
        )
        flash("Aspek diperbarui.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_aspect_route(aspect_id: int) -> Response:
    try:
        aspect = get_hosp_aspect(aspect_id)
        if delete_hosp_aspect(aspect_id):
            asp_name = aspect.get("name") if aspect else f"ID {aspect_id}"
            log_activity(
                user_id=int(current_user().get("id")),
                action="delete",
                target_type="HOSPITALITY_ASPECT",
                target_id=aspect_id,
                target_name=asp_name,
                details={"description": f"Menghapus aspek: {asp_name}"},
            )
            flash("Aspek dihapus/nonaktif.", "success")
        else:
            flash("Aspek tidak ditemukan.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/toggle-active", methods=["POST"])
@role_required("admin")
def admin_toggle_aspect_active(aspect_id: int) -> Response:
    if toggle_aspect_active(aspect_id):
        flash("Status aspek diperbarui.", "success")
    else:
        flash("Aspek tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/toggle-required", methods=["POST"])
@role_required("admin")
def admin_toggle_aspect_required(aspect_id: int) -> Response:
    if toggle_aspect_required(aspect_id):
        flash("Status wajib aspek diperbarui.", "success")
    else:
        flash("Aspek tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspects/reorder", methods=["POST"])
@role_required("admin")
def admin_reorder_aspects() -> Response:
    data = request.get_json(silent=True) or {}
    order_ids = data.get("aspect_ids") or []
    try:
        ids = [int(i) for i in order_ids]
        reorder_hosp_aspects(ids)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@hospitality_bp.route("/admin/review-extra-questions", methods=["GET"])
@role_required("admin")
def admin_review_extra_questions() -> Response:
    questions = list_guestbook_extra_questions(active_only=None)
    activity_logs = fetch_activity_logs(
        limit=50,
        target_types=["HOSPITALITY_REVIEW_EXTRA_QUESTION"],
    )
    return render_template(
        "hospitality/admin/review_extra_questions.html",
        questions=questions,
        activity_logs=activity_logs,
    )


@hospitality_bp.route("/admin/review-extra-questions", methods=["POST"])
@role_required("admin")
def admin_create_review_extra_question() -> Response:
    text = (request.form.get("question_text") or "").strip()
    sort_order = request.form.get("sort_order", type=int) or 0
    if not text:
        flash("Pertanyaan wajib diisi.", "warning")
        return redirect(url_for("hospitality.admin_review_extra_questions"))
    try:
        row = create_guestbook_extra_question(
            question_text=text,
            sort_order=sort_order,
            active=True,
            created_by=int(current_user().get("id")),
        )
        log_activity(
            user_id=int(current_user().get("id")),
            action="create",
            target_type="HOSPITALITY_REVIEW_EXTRA_QUESTION",
            target_id=row.get("id"),
            target_name=text,
            details={"description": f"Membuat pertanyaan tambahan review: {text}"},
        )
        flash("Pertanyaan tambahan berhasil dibuat.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_review_extra_questions"))


@hospitality_bp.route("/admin/review-extra-questions/<int:question_id>", methods=["POST"])
@role_required("admin")
def admin_update_review_extra_question(question_id: int) -> Response:
    existing = get_guestbook_extra_question(question_id)
    if not existing:
        flash("Pertanyaan tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_review_extra_questions"))
    text = (request.form.get("question_text") or existing.get("question_text") or "").strip()
    sort_order = request.form.get("sort_order", type=int)
    if sort_order is None:
        sort_order = int(existing.get("sort_order") or 0)
    active = request.form.get("active") == "on"
    try:
        update_guestbook_extra_question(
            question_id=question_id,
            question_text=text,
            sort_order=sort_order,
            active=active,
        )
        log_activity(
            user_id=int(current_user().get("id")),
            action="update",
            target_type="HOSPITALITY_REVIEW_EXTRA_QUESTION",
            target_id=question_id,
            target_name=text,
            details={"description": f"Memperbarui pertanyaan tambahan review: {text}", "active": active},
        )
        flash("Pertanyaan tambahan diperbarui.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_review_extra_questions"))


@hospitality_bp.route("/admin/review-extra-questions/<int:question_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_review_extra_question(question_id: int) -> Response:
    existing = get_guestbook_extra_question(question_id)
    if not existing:
        flash("Pertanyaan tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_review_extra_questions"))
    try:
        ok = delete_guestbook_extra_question(question_id)
        if ok:
            log_activity(
                user_id=int(current_user().get("id")),
                action="delete",
                target_type="HOSPITALITY_REVIEW_EXTRA_QUESTION",
                target_id=question_id,
                target_name=existing.get("question_text"),
                details={"description": f"Menghapus/nonaktifkan pertanyaan tambahan review: {existing.get('question_text')}"},
            )
            flash("Pertanyaan tambahan dihapus/nonaktif.", "success")
        else:
            flash("Pertanyaan tidak ditemukan.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_review_extra_questions"))


@hospitality_bp.route("/admin/review-extra-questions/<int:question_id>/toggle-active", methods=["POST"])
@role_required("admin")
def admin_toggle_review_extra_question_active(question_id: int) -> Response:
    row = toggle_guestbook_extra_question_active(question_id)
    if row:
        log_activity(
            user_id=int(current_user().get("id")),
            action="toggle_active",
            target_type="HOSPITALITY_REVIEW_EXTRA_QUESTION",
            target_id=question_id,
            target_name=row.get("question_text"),
            details={"description": f"Mengubah status pertanyaan tambahan review: {row.get('question_text')}", "active": row.get("active")},
        )
        flash("Status pertanyaan diperbarui.", "success")
    else:
        flash("Pertanyaan tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_review_extra_questions"))


@hospitality_bp.route("/admin/review-extra-questions/reorder", methods=["POST"])
@role_required("admin")
def admin_reorder_review_extra_questions() -> Response:
    data = request.get_json(silent=True) or {}
    order_ids = data.get("question_ids") or []
    try:
        ids = [int(i) for i in order_ids]
        reorder_guestbook_extra_questions(ids)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
