from __future__ import annotations

from datetime import datetime
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
