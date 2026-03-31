from __future__ import annotations

from datetime import date, datetime
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
    notify_hospitality_verified,
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
    get_component,
    get_hosp_aspect,
    get_latest_reopen_request,
    get_guestbook_review_detail,
    fetch_guestbook_review_bottom_schools,
    fetch_guestbook_review_rating_distribution,
    fetch_guestbook_review_stats,
    fetch_guestbook_review_top_schools,
    fetch_guestbook_review_trend,
    fetch_guestbook_reviews_export,
    list_guestbook_reviews,
    list_assessments_for_school,
    list_assessments_for_staff,
    list_components_with_aspects,
    list_guestbook_candidates,
    list_comments,
    list_reopen_requests,
    link_guestbook_transaction,
    reorder_components,
    reorder_hosp_aspects,
    submit_assessment,
    toggle_aspect_active,
    toggle_aspect_required,
    toggle_component_active,
    toggle_component_required,
    update_component,
    update_hosp_aspect,
    update_reopen_request_status,
    upsert_scores,
)

hospitality_bp = Blueprint(
    "hospitality",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/hospitality",
)

# Reuse portal context (permissions, badges, etc.) so base_portal works on hospitality pages.
@hospitality_bp.context_processor
def inject_portal_context():
    return portal_inject_permissions() or {}


# ===== Helper =====

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


# ===== Routing =====


@hospitality_bp.route("/")
def landing() -> Response:
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    role = (user.get("role") or "").lower()
    if role == "staff":
        return redirect(url_for("hospitality.staff_home"))
    if role == "sekolah":
        return redirect(url_for("hospitality.school_home"))
    return redirect(url_for("hospitality.admin_home"))


@hospitality_bp.route("/staff")
@role_required("staff")
def staff_home() -> Response:
    user = current_user()
    status_filter = (request.args.get("status") or "").strip().lower() or None
    search = (request.args.get("q") or "").strip() or None
    assessments = list_assessments_for_staff(
        staff_id=int(user.get("id")),
        status=status_filter,
        search=search,
    )
    return render_template(
        "hospitality/staff/list.html",
        assessments=assessments,
        score_max=HOSPITALITY_SCORE_MAX,
        status_filter=status_filter or "",
        search_query=search or "",
    )


@hospitality_bp.route("/staff/assess/<int:school_id>", methods=["GET", "POST"])
@role_required("staff")
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

    if request.method == "POST":
        try:
            note_text = (request.form.get("note") or "").strip() or None
            assessment = create_assessment(
                school_id=school_id,
                staff_id=int(user.get("id")),
                score_scale_max=HOSPITALITY_SCORE_MAX,
                note_text=note_text,
            )
            # Parse scores from form: fields score_<aspect_id>
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
            submit_assessment(
                assessment_id=int(assessment["id"]),
                note_text=note_text,
                score_scale_max=HOSPITALITY_SCORE_MAX,
            )
            flash("Penilaian tersimpan. Silakan hubungkan dengan buku tamu untuk verifikasi.", "success")
            return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment["id"]))
        except Exception as exc:  # pragma: no cover
            flash(str(exc), "danger")

    return render_template(
        "hospitality/staff/assess.html",
        school=school,
        components=components,
        score_scale=list(range(1, HOSPITALITY_SCORE_MAX + 1)),
    )


@hospitality_bp.route("/assessment/<int:assessment_id>")
@role_required("staff", "sekolah", "admin", "coordinator")
def assessment_detail(assessment_id: int) -> Response:
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    user = current_user()
    if (user.get("role") == "staff" and int(user.get("id")) != int(assessment.get("staff_id"))):
        abort(403)
    if user.get("role") == "sekolah":
        school = _fetch_user_school(user.get("id"))
        if not school or int(school.get("id")) != int(assessment.get("school_id")):
            abort(403)

    scores = get_assessment_scores(assessment_id)
    components = list_components_with_aspects(active_only=False)
    scores_map = {s.get("aspect_id"): s for s in scores}
    guestbook_options = list_guestbook_candidates(school_id=int(assessment.get("school_id")))
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
        is_staff=user.get("role") == "staff",
        is_school=user.get("role") == "sekolah",
    )


@hospitality_bp.route("/assessment/<int:assessment_id>/link-guestbook", methods=["POST"])
@role_required("staff")
def link_guestbook(assessment_id: int) -> Response:
    user = current_user()
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    if int(assessment.get("staff_id")) != int(user.get("id")):
        abort(403)

    transaction_id = request.form.get("transaction_id", type=int)
    if not transaction_id:
        flash("Pilih transaksi buku tamu.", "warning")
        return redirect(url_for("hospitality.assessment_detail", assessment_id=assessment_id))

    try:
        result = link_guestbook_transaction(
            assessment_id=assessment_id,
            transaction_id=transaction_id,
            linked_by=int(user.get("id")),
        )
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
        notify_hospitality_verified(
            assessment_id=assessment_id,
            school_name=assessment.get("school_name"),
            staff_name=assessment.get("staff_name"),
            transaction_id=transaction_id,
        )
        flash("Berhasil menghubungkan buku tamu dan memverifikasi penilaian.", "success")
    except Exception as exc:  # pragma: no cover
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
@role_required("staff")
def request_reopen(assessment_id: int) -> Response:
    user = current_user()
    reason = (request.form.get("reason") or "").strip() or None
    assessment = get_assessment(assessment_id)
    if not assessment:
        abort(404)
    if user.get("role") == "staff" and int(user.get("id")) != int(assessment.get("staff_id")):
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
    request_id = request.form.get("request_id", type=int)
    if not request_id:
        request_id = get_latest_reopen_request_id(assessment_id)
    if not request_id:
        flash("Permintaan reopen tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_reopen_requests"))
    note = (request.form.get("reviewer_note") or "").strip() or None
    return _update_reopen_status(request_id=request_id, status="approved", reviewer_note=note)


@hospitality_bp.route("/admin/reopen/<int:assessment_id>/reject", methods=["POST"])
@role_required("admin")
def reject_reopen(assessment_id: int) -> Response:
    request_id = request.form.get("request_id", type=int)
    if not request_id:
        request_id = get_latest_reopen_request_id(assessment_id)
    if not request_id:
        flash("Permintaan reopen tidak ditemukan.", "warning")
        return redirect(url_for("hospitality.admin_reopen_requests"))
    note = (request.form.get("reviewer_note") or "").strip() or None
    return _update_reopen_status(request_id=request_id, status="rejected", reviewer_note=note)


def _update_reopen_status(*, request_id: int, status: str, reviewer_note: Optional[str]) -> Response:
    user = current_user()
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
            flash("Status reopen diperbarui.", "success")
        else:
            flash("Permintaan tidak ditemukan.", "warning")
    except Exception as exc:  # pragma: no cover
        flash(str(exc), "danger")
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


@hospitality_bp.route("/guestbook-reviews")
@role_required("admin", "coordinator", "sekolah")
def guestbook_review_dashboard() -> Response:
    user = current_user()
    role = (user.get("role") or "").strip().lower()

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
    )
    stats = fetch_guestbook_review_stats(
        school_id=scope_school_id,
        start_date=start_date,
        end_date=end_date,
    )
    trend = fetch_guestbook_review_trend(days=30, school_id=scope_school_id)
    rating_distribution = fetch_guestbook_review_rating_distribution(school_id=scope_school_id)
    top_schools = []
    bottom_schools = []
    if role in {"admin", "coordinator"} and not scope_school_id:
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

    school_options = _list_active_schools() if role in {"admin", "coordinator"} else []

    start_item = ((page - 1) * per_page + 1) if total_rows else 0
    end_item = min(page * per_page, total_rows) if total_rows else 0

    return render_template(
        "hospitality/guestbook/list.html",
        reviews=reviews,
        stats=stats,
        trend=trend,
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
        is_admin=role in {"admin", "coordinator"},
    )


@hospitality_bp.route("/guestbook-reviews/<int:review_id>")
@role_required("admin", "coordinator", "sekolah")
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
        is_admin=role in {"admin", "coordinator"},
    )


@hospitality_bp.route("/guestbook-reviews/export")
@role_required("admin", "coordinator", "sekolah")
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


@hospitality_bp.route("/admin")
@role_required("admin", "coordinator")
def admin_home() -> Response:
    status = (request.args.get("status") or "").strip().lower() or None
    reopen_requests = list_reopen_requests(status=status, limit=200)
    from .queries import (
        fetch_stats,
        fetch_daily_trend,
        fetch_top_schools,
        fetch_bottom_schools,
        fetch_recent_assessments,
        fetch_linked_photos,
    )
    stats = fetch_stats()
    trend = fetch_daily_trend(days=30)
    top_schools = fetch_top_schools(limit=10)
    bottom_schools = fetch_bottom_schools(limit=10)
    recent = fetch_recent_assessments(limit=20)
    linked_photos = fetch_linked_photos(limit=12)
    return render_template(
        "hospitality/admin/list.html",
        reopen_requests=reopen_requests,
        status_filter=status or "",
        stats=stats,
        trend=trend,
        top_schools=top_schools,
        bottom_schools=bottom_schools,
        recent_assessments=recent,
        linked_photos=linked_photos,
    )


@hospitality_bp.route("/admin/reopen-requests")
@role_required("admin", "coordinator")
def admin_reopen_requests() -> Response:
    status = (request.args.get("status") or "").strip().lower() or None
    requests = list_reopen_requests(status=status, limit=500)
    return render_template(
        "hospitality/admin/reopen_requests.html",
        reopen_requests=requests,
        status_filter=status or "",
    )


@hospitality_bp.route("/admin/export")
@role_required("admin", "coordinator")
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
@role_required("admin", "coordinator")
def admin_setup() -> Response:
    components = list_components_with_aspects(active_only=False)
    return render_template(
        "hospitality/admin/setup.html",
        components=components,
    )


@hospitality_bp.route("/admin/setup/component", methods=["POST"])
@role_required("admin", "coordinator")
def admin_create_component() -> Response:
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    if not name:
        flash("Nama komponen wajib diisi.", "warning")
        return redirect(url_for("hospitality.admin_setup"))
    try:
        create_component(name=name, description=description, sort_order=0, is_required=True, active=True)
        flash("Komponen ditambahkan.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>", methods=["POST"])
@role_required("admin", "coordinator")
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
        flash("Komponen diperbarui.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/delete", methods=["POST"])
@role_required("admin", "coordinator")
def admin_delete_component(component_id: int) -> Response:
    try:
        if delete_component(component_id):
            flash("Komponen dihapus/nonaktif.", "success")
        else:
            flash("Komponen tidak ditemukan.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/toggle-active", methods=["POST"])
@role_required("admin", "coordinator")
def admin_toggle_component_active(component_id: int) -> Response:
    if toggle_component_active(component_id):
        flash("Status komponen diperbarui.", "success")
    else:
        flash("Komponen tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/component/<int:component_id>/toggle-required", methods=["POST"])
@role_required("admin", "coordinator")
def admin_toggle_component_required(component_id: int) -> Response:
    if toggle_component_required(component_id):
        flash("Status wajib komponen diperbarui.", "success")
    else:
        flash("Komponen tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/components/reorder", methods=["POST"])
@role_required("admin", "coordinator")
def admin_reorder_components() -> Response:
    data = request.get_json(silent=True) or {}
    order_ids = data.get("component_ids") or []
    try:
        ids = [int(i) for i in order_ids]
        reorder_components(ids)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@hospitality_bp.route("/admin/setup/aspect", methods=["POST"])
@role_required("admin", "coordinator")
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
        create_hosp_aspect(
            component_id=component_id,
            name=name,
            description=description,
            sort_order=sort_order,
            is_required=is_required,
            active=True,
        )
        flash("Aspek ditambahkan.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>", methods=["POST"])
@role_required("admin", "coordinator")
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
        flash("Aspek diperbarui.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/delete", methods=["POST"])
@role_required("admin", "coordinator")
def admin_delete_aspect_route(aspect_id: int) -> Response:
    try:
        if delete_hosp_aspect(aspect_id):
            flash("Aspek dihapus/nonaktif.", "success")
        else:
            flash("Aspek tidak ditemukan.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/toggle-active", methods=["POST"])
@role_required("admin", "coordinator")
def admin_toggle_aspect_active(aspect_id: int) -> Response:
    if toggle_aspect_active(aspect_id):
        flash("Status aspek diperbarui.", "success")
    else:
        flash("Aspek tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspect/<int:aspect_id>/toggle-required", methods=["POST"])
@role_required("admin", "coordinator")
def admin_toggle_aspect_required(aspect_id: int) -> Response:
    if toggle_aspect_required(aspect_id):
        flash("Status wajib aspek diperbarui.", "success")
    else:
        flash("Aspek tidak ditemukan.", "warning")
    return redirect(url_for("hospitality.admin_setup"))


@hospitality_bp.route("/admin/setup/aspects/reorder", methods=["POST"])
@role_required("admin", "coordinator")
def admin_reorder_aspects() -> Response:
    data = request.get_json(silent=True) or {}
    order_ids = data.get("aspect_ids") or []
    try:
        ids = [int(i) for i in order_ids]
        reorder_hosp_aspects(ids)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
