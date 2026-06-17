from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for

from dashboard.auth import current_user, role_required
from dashboard.queries import (
    call_spmb_queue_number,
    cancel_spmb_queue_call,
    claim_spmb_table_assignment,
    get_spmb_queue_counter,
    get_spmb_table_claim_for_user,
    list_spmb_queue_numbers,
    list_spmb_staff_queue_status,
    list_spmb_table_assignments,
    record_admin_action,
    release_spmb_table_assignment,
)
from utils import current_jakarta_time

penugasan_bp = Blueprint(
    "penugasan",
    __name__,
    template_folder="templates",
    url_prefix="/penugasan",
)


def _parse_date_only(value: Optional[str]):
    clean = (value or "").strip()
    if not clean:
        return current_jakarta_time().date()
    try:
        return datetime.strptime(clean, "%Y-%m-%d").date()
    except ValueError:
        return current_jakarta_time().date()


def _announcement_text(queue_number: int, table_number: int) -> str:
    return f"Nomor antrian {queue_number}, silakan menuju meja nomor {table_number}."


@penugasan_bp.route("/")
@role_required("admin", "coordinator", "staff")
def index() -> Response:
    return redirect(url_for("penugasan.spmb_queue_picker"))


@penugasan_bp.route("/spmb-table-claim", methods=["GET", "POST"])
@role_required("admin", "coordinator", "staff")
def spmb_table_claim() -> Response:
    user = current_user() or {}
    selected_date = _parse_date_only(request.form.get("assignment_date") or request.args.get("date"))

    if request.method == "POST":
        action = (request.form.get("action") or "claim").strip()
        try:
            if action == "release":
                deleted_count = release_spmb_table_assignment(
                    assignment_date=selected_date,
                    user_id=int(user.get("id")),
                )
                if deleted_count:
                    flash("Klaim meja berhasil dilepas.", "success")
                else:
                    flash("Belum ada meja yang diklaim pada tanggal ini.", "info")
            else:
                table_number = int(request.form.get("table_number") or 0)
                result = claim_spmb_table_assignment(
                    assignment_date=selected_date,
                    table_number=table_number,
                    user_id=int(user.get("id")),
                )
                flash(result["message"], "success" if result.get("success") else "warning")

            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="UPDATE",
                target_type="SPMB_TABLE_CLAIM",
                target_name=selected_date.isoformat(),
                metadata={
                    "assignment_date": selected_date.isoformat(),
                    "action": action,
                    "table_number": request.form.get("table_number"),
                    "role": user.get("role"),
                },
            )
        except Exception as exc:
            current_app.logger.exception("Failed to process SPMB table claim")
            flash(f"Gagal memproses klaim meja: {exc}", "danger")
        return redirect(url_for("penugasan.spmb_table_claim", date=selected_date.isoformat()))

    assignments = list_spmb_table_assignments(selected_date)
    my_assignment = next(
        (
            item
            for item in assignments
            if item.get("officer_user_id") and int(item["officer_user_id"]) == int(user.get("id"))
        ),
        None,
    )
    return render_template(
        "penugasan/spmb_table_claim.html",
        selected_date=selected_date,
        assignments=assignments,
        my_assignment=my_assignment,
    )


@penugasan_bp.route("/pilih-antrian", methods=["GET", "POST"])
@role_required("admin", "coordinator", "staff")
def spmb_queue_picker() -> Response:
    user = current_user() or {}
    selected_date = _parse_date_only(request.form.get("service_date") or request.args.get("date"))
    my_assignment = get_spmb_table_claim_for_user(
        assignment_date=selected_date,
        user_id=int(user.get("id")),
    )

    if request.method == "POST":
        if not my_assignment:
            flash("Klaim meja operator terlebih dahulu sebelum memilih antrian.", "warning")
            return redirect(url_for("penugasan.spmb_table_claim", date=selected_date.isoformat()))

        try:
            action = (request.form.get("action") or "call").strip().lower()
            queue_number = int(request.form.get("queue_number") or 0)
            table_number = int(my_assignment["table_number"])
            if action == "cancel":
                call = cancel_spmb_queue_call(
                    service_date=selected_date,
                    queue_number=queue_number,
                    officer_user_id=int(user.get("id")),
                )
                if call:
                    record_admin_action(
                        user_id=user.get("id"),
                        feature_key="aska_insight",
                        action="UPDATE",
                        target_type="SPMB_QUEUE_CALL",
                        target_id=call.get("id"),
                        target_name=f"{selected_date.isoformat()} #{call.get('queue_number')}",
                        metadata={
                            "service_date": selected_date.isoformat(),
                            "queue_number": call.get("queue_number"),
                            "table_number": call.get("table_number"),
                            "status": call.get("status"),
                            "action": "cancel",
                        },
                    )
                    flash(f"Nomor antrian {call['queue_number']} dikembalikan tidak aktif.", "success")
                else:
                    flash("Panggilan aktif tidak ditemukan atau bukan milik meja Anda.", "warning")
                return redirect(url_for("penugasan.spmb_queue_picker", date=selected_date.isoformat()))

            call = call_spmb_queue_number(
                service_date=selected_date,
                queue_number=queue_number,
                table_number=table_number,
                officer_user_id=int(user.get("id")),
            )
            announcement = _announcement_text(
                int(call["queue_number"]),
                int(call["table_number"]),
            )
            record_admin_action(
                user_id=user.get("id"),
                feature_key="aska_insight",
                action="UPDATE",
                target_type="SPMB_QUEUE_CALL",
                target_id=call.get("id"),
                target_name=f"{selected_date.isoformat()} #{call.get('queue_number')}",
                metadata={
                    "service_date": selected_date.isoformat(),
                    "queue_number": call.get("queue_number"),
                    "table_number": call.get("table_number"),
                    "status": call.get("status"),
                },
            )
            flash(f"Nomor antrian {call['queue_number']} dipanggil ke meja {call['table_number']}.", "success")
            return redirect(
                url_for(
                    "penugasan.spmb_queue_picker",
                    date=selected_date.isoformat(),
                    announce=announcement,
                )
            )
        except ValueError as exc:
            flash(str(exc), "warning")
        except Exception as exc:
            current_app.logger.exception("Failed to call SPMB queue")
            flash(f"Gagal memilih antrian: {exc}", "danger")
        return redirect(url_for("penugasan.spmb_queue_picker", date=selected_date.isoformat()))

    queue_counter = get_spmb_queue_counter(selected_date)
    queue_items = list_spmb_queue_numbers(service_date=selected_date)
    staff_queue_statuses = list_spmb_staff_queue_status(service_date=selected_date)
    return render_template(
        "penugasan/spmb_queue_picker.html",
        selected_date=selected_date,
        my_assignment=my_assignment,
        queue_counter=queue_counter,
        queue_items=queue_items,
        staff_queue_statuses=staff_queue_statuses,
        announcement=request.args.get("announce", ""),
    )
