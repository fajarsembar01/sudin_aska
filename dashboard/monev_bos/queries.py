from dashboard.db_access import get_cursor
from typing import List, Dict, Any, Optional
from datetime import date

# --- PERIODS ---

# Default TW date ranges (fixed)
_TW_RANGES = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}

def ensure_periods_for_year(year: int) -> None:
    """Auto-generate TW 1-4 for a given year, fixing dates if they already exist."""
    with get_cursor(commit=True) as cur:
        for tw in range(1, 5):
            start_str, end_str = _TW_RANGES[tw]
            start_date = date.fromisoformat(f"{year}-{start_str}")
            end_date = date.fromisoformat(f"{year}-{end_str}")
            cur.execute(
                """
                INSERT INTO monev_bos_periods (year, tw, start_date, end_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (year, tw) DO UPDATE 
                SET start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date
                """,
                (year, tw, start_date, end_date)
            )

def list_periods() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods ORDER BY year DESC, tw ASC")
        return [dict(row) for row in cur.fetchall()]

def list_periods_by_year(year: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE year = %s ORDER BY tw ASC", (year,))
        return [dict(row) for row in cur.fetchall()]

def get_available_years() -> List[int]:
    with get_cursor() as cur:
        cur.execute("SELECT DISTINCT year FROM monev_bos_periods ORDER BY year DESC")
        return [row[0] for row in cur.fetchall()]

def get_active_period() -> Optional[Dict[str, Any]]:
    """Get the first active period (backward compat)."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE is_active = TRUE ORDER BY tw ASC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None

def get_active_periods() -> List[Dict[str, Any]]:
    """Get all active periods."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_periods WHERE is_active = TRUE ORDER BY year DESC, tw ASC")
        return [dict(row) for row in cur.fetchall()]

def set_active_period(period_id: int) -> None:
    """Activate a single period (without deactivating others)."""
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE monev_bos_periods SET is_active = TRUE WHERE id = %s", (period_id,))

def deactivate_period(period_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE monev_bos_periods SET is_active = FALSE WHERE id = %s", (period_id,))

def update_period_deadline(period_id: int, deadline: date) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_periods SET end_date = %s WHERE id = %s",
            (deadline, period_id)
        )

# --- CHECKLISTS ---
def list_checklists(include_inactive: bool = False) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = "SELECT * FROM monev_bos_checklists"
        if not include_inactive:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY sort_order ASC, id ASC"
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]

def create_checklist(name: str, description: str, sort_order: int) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_checklists (name, description, sort_order)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (name, description, sort_order)
        )
        return cur.fetchone()[0]

def update_checklist(checklist_id: int, name: str, description: str, sort_order: int, is_active: bool) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_checklists
            SET name = %s, description = %s, sort_order = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name, description, sort_order, is_active, checklist_id)
        )

def delete_checklist(checklist_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_checklists WHERE id = %s", (checklist_id,))

# --- TEAMS ---
def list_teams() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.*, u.full_name as leader_name, u.email as leader_email
            FROM monev_bos_teams t
            LEFT JOIN dashboard_users u ON t.leader_id = u.id
            ORDER BY t.name ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]

def create_team(name: str, leader_id: Optional[int]) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO monev_bos_teams (name, leader_id) VALUES (%s, %s) RETURNING id",
            (name, leader_id)
        )
        return cur.fetchone()[0]

def delete_team(team_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_teams WHERE id = %s", (team_id,))

def update_team_leader(team_id: int, leader_id: Optional[int]) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_teams SET leader_id = %s, updated_at = NOW() WHERE id = %s",
            (leader_id, team_id)
        )

# --- ASSIGNMENTS ---
def list_assignments(period_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, t.name as team_name, s.full_name as school_name, s.email as school_email
            FROM monev_bos_assignments a
            JOIN monev_bos_teams t ON a.team_id = t.id
            JOIN dashboard_users s ON a.school_id = s.id
            WHERE a.period_id = %s
            ORDER BY s.full_name ASC
            """,
            (period_id,)
        )
        return [dict(row) for row in cur.fetchall()]

def assign_team_to_school(team_id: int, school_id: int, period_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_assignments (team_id, school_id, period_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (school_id, period_id) DO UPDATE SET team_id = EXCLUDED.team_id
            """,
            (team_id, school_id, period_id)
        )

def unassign_school(assignment_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_assignments WHERE id = %s", (assignment_id,))

# --- USERS ---
def get_staff_users() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, email FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved' ORDER BY full_name"
        )
        return [dict(row) for row in cur.fetchall()]

def get_sekolah_users() -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, email FROM dashboard_users WHERE role = 'sekolah' AND account_status = 'approved' ORDER BY full_name"
        )
        return [dict(row) for row in cur.fetchall()]

# --- REPORTS (SEKOLAH) ---
def get_school_report(school_id: int, period_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_reports WHERE school_id = %s AND period_id = %s", (school_id, period_id))
        row = cur.fetchone()
        return dict(row) if row else None

def save_school_report_receipts(school_id: int, period_id: int, bosp_amount: float, bop_amount: float) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_reports (school_id, period_id, bosp_receipt_amount, bop_receipt_amount)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (school_id, period_id) DO UPDATE 
            SET bosp_receipt_amount = EXCLUDED.bosp_receipt_amount,
                bop_receipt_amount = EXCLUDED.bop_receipt_amount,
                updated_at = NOW()
            RETURNING id
            """,
            (school_id, period_id, bosp_amount, bop_amount)
        )
        return cur.fetchone()[0]

def submit_school_report(report_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_reports SET status = 'submitted', submitted_at = NOW(), updated_at = NOW() WHERE id = %s",
            (report_id,)
        )

# --- ACTIVITIES ---
def list_activities(report_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, 
                   u.full_name AS auditor_name
            FROM monev_bos_activities a
            LEFT JOIN LATERAL (
                SELECT l.user_id, du.full_name
                FROM monev_bos_audit_logs l
                JOIN dashboard_users du ON l.user_id = du.id
                WHERE l.activity_id = a.id AND l.action = 'VALIDATE'
                ORDER BY l.created_at DESC
                LIMIT 1
            ) u ON TRUE
            WHERE a.report_id = %s
            ORDER BY a.fund_source, a.activity_code
            """,
            (report_id,)
        )
        return [dict(row) for row in cur.fetchall()]

def create_activity(report_id: int, fund_source: str, data: Dict[str, Any]) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_activities 
            (report_id, fund_source, activity_code, activity_name, realized_amount, vendor_name, bku_number, item_name, item_specs, item_quantity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                report_id, fund_source, data['activity_code'], data['activity_name'],
                data['realized_amount'], data.get('vendor_name'), data.get('bku_number'),
                data.get('item_name'), data.get('item_specs'), data.get('item_quantity')
            )
        )
        return cur.fetchone()[0]

def update_activity(activity_id: int, data: Dict[str, Any]) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_activities 
            SET activity_code = %s, activity_name = %s, realized_amount = %s,
                vendor_name = %s, bku_number = %s, item_name = %s, item_specs = %s, item_quantity = %s
            WHERE id = %s
            """,
            (
                data['activity_code'], data['activity_name'], data['realized_amount'],
                data.get('vendor_name'), data.get('bku_number'),
                data.get('item_name'), data.get('item_specs'), data.get('item_quantity'),
                activity_id
            )
        )

def get_activity_by_id(activity_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_activities WHERE id = %s", (activity_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def delete_activity(activity_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_activities WHERE id = %s", (activity_id,))

# --- ACTIVITY HISTORY ---
def save_activity_history(activity_id: int, changed_by: int, reason: str = None) -> None:
    """Snapshot data kegiatan saat ini sebelum diubah."""
    import json
    with get_cursor(commit=True) as cur:
        # Ambil data kegiatan saat ini
        cur.execute("SELECT * FROM monev_bos_activities WHERE id = %s", (activity_id,))
        row = cur.fetchone()
        if not row:
            return
        act = dict(row)
        previous_data = {
            "activity_code": act.get("activity_code"),
            "activity_name": act.get("activity_name"),
            "realized_amount": str(act.get("realized_amount", 0)),
            "vendor_name": act.get("vendor_name"),
            "bku_number": act.get("bku_number"),
            "item_name": act.get("item_name"),
            "item_specs": act.get("item_specs"),
            "item_quantity": act.get("item_quantity"),
        }
        cur.execute(
            """
            INSERT INTO monev_bos_activity_history (activity_id, changed_by, previous_data, change_reason, activity_status_at_change)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (activity_id, changed_by, json.dumps(previous_data), reason, act.get("status"))
        )

def get_activity_history(activity_id: int) -> List[Dict[str, Any]]:
    """Ambil semua riwayat perubahan data suatu kegiatan."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT h.*, u.full_name as changed_by_name, u.email as changed_by_email
            FROM monev_bos_activity_history h
            JOIN dashboard_users u ON h.changed_by = u.id
            WHERE h.activity_id = %s
            ORDER BY h.created_at DESC
            """,
            (activity_id,)
        )
        return [dict(row) for row in cur.fetchall()]


def create_edit_request(activity_id: int, requested_by: int, reason: str, requested_data: Optional[dict] = None) -> int:
    import json
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_edit_requests (activity_id, requested_by, reason, requested_data, status)
            VALUES (%s, %s, %s, %s, 'pending') RETURNING id
            """,
            (activity_id, requested_by, reason, json.dumps(requested_data) if requested_data is not None else None)
        )
        return cur.fetchone()[0]

def get_edit_request_by_activity(activity_id: int) -> Optional[Dict[str, Any]]:
    """Get latest pending edit request for an activity."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM monev_bos_edit_requests WHERE activity_id = %s AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (activity_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_pending_edit_requests_count() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM monev_bos_edit_requests WHERE status = 'pending'")
        return cur.fetchone()[0]

def get_submitted_reports_count() -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM monev_bos_reports WHERE status = 'submitted'")
        return cur.fetchone()[0]

def list_edit_requests(status: str = None) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        if status:
            cur.execute(
                """
                SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.status as activity_status,
                       r.id as report_id, u.full_name as requester_name, u.email as requester_email,
                       s.full_name as school_name
                FROM monev_bos_edit_requests er
                JOIN monev_bos_activities a ON er.activity_id = a.id
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users u ON er.requested_by = u.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE er.status = %s
                ORDER BY er.created_at DESC
                """,
                (status,)
            )
        else:
            cur.execute(
                """
                SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.status as activity_status,
                       r.id as report_id, u.full_name as requester_name, u.email as requester_email,
                       s.full_name as school_name
                FROM monev_bos_edit_requests er
                JOIN monev_bos_activities a ON er.activity_id = a.id
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users u ON er.requested_by = u.id
                JOIN dashboard_users s ON r.school_id = s.id
                ORDER BY er.created_at DESC
                """
            )
        return [dict(row) for row in cur.fetchall()]

def get_edit_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT er.*, a.activity_code, a.activity_name, a.fund_source, a.report_id,
                   u.full_name as requester_name, s.full_name as school_name
            FROM monev_bos_edit_requests er
            JOIN monev_bos_activities a ON er.activity_id = a.id
            JOIN monev_bos_reports r ON a.report_id = r.id
            JOIN dashboard_users u ON er.requested_by = u.id
            JOIN dashboard_users s ON r.school_id = s.id
            WHERE er.id = %s
            """,
            (request_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def send_reopen_notification_to_staff(activity_id: int, review_notes: str = None) -> None:
    """Kirim notifikasi in-app ke Staff Auditor yang bertugas bahwa kegiatan telah di-reopen untuk validasi ulang."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT a.id as activity_id, a.activity_code, a.activity_name, a.fund_source,
                       r.id as report_id, r.school_id, r.period_id, s.full_name as school_name
                FROM monev_bos_activities a
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE a.id = %s
                """,
                (activity_id,)
            )
            act = cur.fetchone()
            if not act:
                return
            act = dict(act)

            # 1. Staff dari tim penugasan sekolah ini
            cur.execute(
                """
                SELECT DISTINCT tm.staff_id
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                WHERE ass.school_id = %s AND ass.period_id = %s
                """,
                (act['school_id'], act['period_id'])
            )
            team_staff = [r[0] for r in cur.fetchall() if r[0]]

            # 2. Staff yang sebelumnya pernah melakukan audit / validasi pada laporan ini
            cur.execute(
                """
                SELECT DISTINCT l.user_id
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                """,
                (act['report_id'],)
            )
            previous_auditors = [r[0] for r in cur.fetchall() if r[0]]

            staff_ids = list(set(team_staff + previous_auditors))

            # Jika tidak ada penugasan tim spesifik maupun auditor terdahulu, kirim ke semua user role 'staff'
            if not staff_ids:
                cur.execute("SELECT id FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved'")
                staff_ids = [r[0] for r in cur.fetchall() if r[0]]

            title = f"Reopen Audit: {act['activity_code']}"
            message = f"Kegiatan {act['activity_code']} ({act['school_name']}) telah di-reopen oleh admin untuk revisi. Silakan lakukan validasi ulang setelah sekolah memperbarui data."
            if review_notes:
                message += f" Catatan admin: {review_notes}"
            link = f"/monev-bos/staff/audit/{act['report_id']}"

            for staff_id in staff_ids:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, category, title, message, status, link, reference_table, reference_id, created_at)
                    VALUES (%s, 'monev_bos', %s, %s, 'unread', %s, 'monev_bos_activities', %s, NOW())
                    """,
                    (staff_id, title, message, link, activity_id)
                )
    except Exception as e:
        print(f"Error sending staff notification: {e}")

def send_revised_activity_notification_to_staff(activity_id: int) -> None:
    """Kirim notifikasi in-app ke Staff Auditor bahwa sekolah telah selesai merevisi/memperbarui data kegiatan dan siap divalidasi ulang."""
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT a.id as activity_id, a.activity_code, a.activity_name, a.fund_source,
                       r.id as report_id, r.school_id, r.period_id, s.full_name as school_name
                FROM monev_bos_activities a
                JOIN monev_bos_reports r ON a.report_id = r.id
                JOIN dashboard_users s ON r.school_id = s.id
                WHERE a.id = %s
                """,
                (activity_id,)
            )
            act = cur.fetchone()
            if not act:
                return
            act = dict(act)

            # 1. Staff dari tim penugasan sekolah ini
            cur.execute(
                """
                SELECT DISTINCT tm.staff_id
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                WHERE ass.school_id = %s AND ass.period_id = %s
                """,
                (act['school_id'], act['period_id'])
            )
            team_staff = [r[0] for r in cur.fetchall() if r[0]]

            # 2. Staff yang sebelumnya pernah melakukan audit / validasi pada laporan ini
            cur.execute(
                """
                SELECT DISTINCT l.user_id
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                """,
                (act['report_id'],)
            )
            previous_auditors = [r[0] for r in cur.fetchall() if r[0]]

            staff_ids = list(set(team_staff + previous_auditors))

            # Jika tidak ada penugasan tim spesifik maupun auditor terdahulu, kirim ke semua user role 'staff'
            if not staff_ids:
                cur.execute("SELECT id FROM dashboard_users WHERE role = 'staff' AND account_status = 'approved'")
                staff_ids = [r[0] for r in cur.fetchall() if r[0]]

            title = f"Perbaikan Kegiatan: {act['activity_code']}"
            message = f"{act['school_name']} telah memperbarui data kegiatan {act['activity_code']} ({act['activity_name']}). Silakan lakukan validasi ulang."
            link = f"/monev-bos/staff/audit/{act['report_id']}"

            for staff_id in staff_ids:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, category, title, message, status, link, reference_table, reference_id, created_at)
                    VALUES (%s, 'monev_bos', %s, %s, 'unread', %s, 'monev_bos_activities', %s, NOW())
                    """,
                    (staff_id, title, message, link, activity_id)
                )
    except Exception as e:
        print(f"Error sending staff revised activity notification: {e}")

def approve_edit_request(request_id: int, reviewed_by: int, review_notes: str = None) -> None:
    """Setujui pengajuan reopen edit: simpan history data saat ini & ubah status kegiatan ke 'invalid' (Revisi) agar sekolah dapat mengedit."""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM monev_bos_edit_requests WHERE id = %s", (request_id,))
        req = cur.fetchone()
        if not req:
            return
        req = dict(req)
        activity_id = req['activity_id']

        # 1. Simpan snapshot data kegiatan saat ini ke history sebelum kunci dibuka
        save_activity_history(activity_id, req['requested_by'], reason=f"Reopen oleh Admin (Alasan Sekolah: {req.get('reason') or '-'})")

        # 2. Ubah status kegiatan menjadi 'invalid' (Revisi) agar sekolah bisa edit langsung
        cur.execute(
            """
            UPDATE monev_bos_activities
            SET status = 'invalid', audit_notes = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (review_notes or "Kunci edit dibuka oleh admin. Silakan perbarui data kegiatan.", activity_id)
        )

        # 3. Tandai pengajuan sebagai approved
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'approved', reviewed_by = %s, review_notes = %s, updated_at = NOW() WHERE id = %s",
            (reviewed_by, review_notes, request_id)
        )

    # 4. Kirim notifikasi in-app ke Staff Auditor yang bertugas
    send_reopen_notification_to_staff(activity_id, review_notes)

def reject_edit_request(request_id: int, reviewed_by: int, review_notes: str = None) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'rejected', reviewed_by = %s, review_notes = %s, updated_at = NOW() WHERE id = %s",
            (reviewed_by, review_notes, request_id)
        )

def cancel_edit_request(activity_id: int) -> None:
    """Cancel any pending edit requests for an activity (e.g., when school re-edits)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_edit_requests SET status = 'rejected', updated_at = NOW() WHERE activity_id = %s AND status = 'pending'",
            (activity_id,)
        )



# --- ACTIVITY DOCS ---
def get_activity_docs(activity_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_activity_docs WHERE activity_id = %s", (activity_id,))
        return [dict(row) for row in cur.fetchall()]

def add_activity_doc(activity_id: int, doc_type: str, file_path: str, file_size: int, user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        # Menghapus dokumen dengan tipe yang sama (jika re-upload) kecuali untuk live_photo/physical_proof (bisa banyak)
        if doc_type in ['transfer', 'invoice', 'field_photo']:
            cur.execute("DELETE FROM monev_bos_activity_docs WHERE activity_id = %s AND doc_type = %s", (activity_id, doc_type))
            
        cur.execute(
            """
            INSERT INTO monev_bos_activity_docs (activity_id, doc_type, file_path, file_size, uploaded_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (activity_id, doc_type, file_path, file_size, user_id)
        )
# --- STAFF TEAMS & MEMBERS ---
def get_teams_for_staff(staff_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT t.*, 
                   (t.leader_id = %s) as is_leader
            FROM monev_bos_teams t
            LEFT JOIN monev_bos_team_members tm ON t.id = tm.team_id
            WHERE t.leader_id = %s OR tm.staff_id = %s
            GROUP BY t.id
            ORDER BY t.name ASC
            """,
            (staff_id, staff_id, staff_id)
        )
        return [dict(row) for row in cur.fetchall()]

def get_team_members(team_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.full_name, u.email, u.role
            FROM monev_bos_team_members tm
            JOIN dashboard_users u ON tm.staff_id = u.id
            WHERE tm.team_id = %s
            ORDER BY u.full_name ASC
            """,
            (team_id,)
        )
        return [dict(row) for row in cur.fetchall()]

def add_team_member(team_id: int, staff_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO monev_bos_team_members (team_id, staff_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team_id, staff_id)
        )

def remove_team_member(team_id: int, staff_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM monev_bos_team_members WHERE team_id = %s AND staff_id = %s",
            (team_id, staff_id)
        )

# --- AUDIT (STAFF) ---
def get_schools_for_team(team_id: int, period_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.id as school_id, s.full_name as school_name, 
                   r.id as report_id, r.status as report_status,
                   r.bosp_receipt_amount, r.bop_receipt_amount,
                   (SELECT COUNT(*) FROM monev_bos_activities a WHERE a.report_id = r.id) as total_activities,
                   (SELECT COUNT(*) FROM monev_bos_activities a WHERE a.report_id = r.id AND a.status IN ('valid', 'invalid')) as audited_activities
            FROM monev_bos_assignments a
            JOIN dashboard_users s ON a.school_id = s.id
            LEFT JOIN monev_bos_reports r ON r.school_id = s.id AND r.period_id = a.period_id
            WHERE a.team_id = %s AND a.period_id = %s
            ORDER BY s.full_name ASC
            """,
            (team_id, period_id)
        )
        return [dict(row) for row in cur.fetchall()]

def get_auditor_staff_wa_for_report(report_id: int, school_id: int, period_id: int, activity_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieves staff auditor name and WhatsApp phone number who specifically audited/validated this activity or report."""
    with get_cursor() as cur:
        staff_row = None
        # 1. Staff who validated/audited this SPECIFIC activity
        if activity_id:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.activity_id = %s AND u.role IN ('staff', 'admin')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                ORDER BY l.id DESC
                LIMIT 1
                """,
                (activity_id,)
            )
            staff_row = cur.fetchone()

        # 2. Staff who logged audit actions for this report
        if not staff_row:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_audit_logs l
                JOIN dashboard_users u ON l.user_id = u.id
                WHERE l.report_id = %s AND u.role IN ('staff', 'admin')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                ORDER BY l.id DESC
                LIMIT 1
                """,
                (report_id,)
            )
            staff_row = cur.fetchone()

        # 3. If not found in audit logs, check team assignment
        if not staff_row:
            cur.execute(
                """
                SELECT u.id, u.full_name, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM monev_bos_assignments ass
                JOIN monev_bos_team_members tm ON ass.team_id = tm.team_id
                JOIN dashboard_users u ON tm.staff_id = u.id
                WHERE ass.school_id = %s AND ass.period_id = %s
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                LIMIT 1
                """,
                (school_id, period_id)
            )
            staff_row = cur.fetchone()

        if not staff_row:
            return {}

        s = dict(staff_row)
        phone_raw = s.get("phone") or ""
        phone_formatted = "".join([c for c in str(phone_raw) if c.isdigit()])
        if phone_formatted.startswith("0"):
            phone_formatted = "62" + phone_formatted[1:]

        return {
            "staff_id": s.get("id"),
            "staff_name": s.get("full_name") or "Staff Audit",
            "staff_phone": phone_formatted
        }

def get_school_kecamatan_and_admin_wa(school_user_id: int) -> Dict[str, Any]:
    """Retrieves school kecamatan name and primary admin/coordinator WA number for that kecamatan from portal_kontak table."""
    with get_cursor() as cur:
        # Join portal_schools specifically on s.id = u.school_id
        cur.execute(
            """
            SELECT u.id as user_id, u.full_name as school_name, k.id as kecamatan_id, k.name as kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_schools s ON s.id = u.school_id
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            WHERE u.id = %s
            """,
            (school_user_id,)
        )
        row = cur.fetchone()
        school_info = dict(row) if row and row.get("kecamatan_name") else {}

        # Fallback if u.school_id is null or has no kecamatan
        if not school_info.get("kecamatan_name"):
            cur.execute(
                """
                SELECT u.id as user_id, u.full_name as school_name, k.id as kecamatan_id, k.name as kecamatan_name
                FROM dashboard_users u
                LEFT JOIN portal_schools s ON s.id = u.id
                LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
                LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
                WHERE u.id = %s
                """,
                (school_user_id,)
            )
            row2 = cur.fetchone()
            if row2 and row2.get("kecamatan_name"):
                school_info = dict(row2)

        kec_id = school_info.get("kecamatan_id")
        kec_name = (school_info.get("kecamatan_name") or "Wilayah").strip()

        # 1. First priority: Check portal_kontak table (Kontak Per Wilayah /portal/kontak)
        admin_name = "Admin Wilayah"
        phone_raw = ""
        admin_id = None

        cur.execute(
            """
            SELECT * FROM portal_kontak WHERE UPPER(TRIM(wilayah)) = UPPER(TRIM(%s)) LIMIT 1
            """,
            (kec_name,)
        )
        pk = cur.fetchone()
        if pk:
            pk = dict(pk)
            if pk.get("kontak_1_active") and pk.get("kontak"):
                admin_name = pk.get("nama") or "Admin Wilayah"
                phone_raw = pk.get("kontak")
            elif pk.get("kontak_2_active") and pk.get("kontak_2"):
                admin_name = pk.get("nama_2") or "Admin Wilayah"
                phone_raw = pk.get("kontak_2")
            elif pk.get("kontak"):
                admin_name = pk.get("nama") or "Admin Wilayah"
                phone_raw = pk.get("kontak")

        # 2. Fallback priority: Check user_kecamatan / dashboard_users table
        if not phone_raw:
            cur.execute(
                """
                SELECT u.id, u.full_name, u.role, COALESCE(u.whatsapp_number, u.phone) as phone
                FROM dashboard_users u
                LEFT JOIN user_kecamatan uk ON u.id = uk.user_id
                WHERE u.account_status = 'approved'
                  AND u.role IN ('coordinator', 'admin', 'staff')
                  AND COALESCE(u.whatsapp_number, u.phone) IS NOT NULL
                  AND COALESCE(u.whatsapp_number, u.phone) <> ''
                  AND (uk.kecamatan_id = %s OR u.kecamatan_id = %s OR u.requested_kecamatan = %s OR LOWER(u.kecamatan) = LOWER(%s))
                ORDER BY CASE WHEN u.role = 'coordinator' THEN 1 WHEN u.role = 'staff' THEN 2 ELSE 3 END
                LIMIT 1
                """,
                (kec_id, kec_id, kec_id, kec_name)
            )
            admin_row = cur.fetchone()
            if admin_row:
                admin_info = dict(admin_row)
                admin_id = admin_info.get("id")
                admin_name = admin_info.get("full_name") or "Admin Wilayah"
                phone_raw = admin_info.get("phone") or ""

        phone_formatted = "".join([c for c in str(phone_raw) if c.isdigit()])
        if phone_formatted.startswith("0"):
            phone_formatted = "62" + phone_formatted[1:]

        return {
            "school_name": school_info.get("school_name") or "Sekolah",
            "kecamatan_id": kec_id,
            "kecamatan_name": kec_name,
            "admin_id": admin_id,
            "admin_name": admin_name,
            "admin_phone": phone_formatted,
        }

def get_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.*, s.full_name as school_name
            FROM monev_bos_reports r
            JOIN dashboard_users s ON r.school_id = s.id
            WHERE r.id = %s
            """,
            (report_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def update_activity_audit(activity_id: int, status: str, notes: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE monev_bos_activities SET status = %s, audit_notes = %s, updated_at = NOW() WHERE id = %s",
            (status, notes, activity_id)
        )

def save_checklist_result(activity_id: int, checklist_id: int, status: str, notes: str, user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_checklist_results (activity_id, checklist_id, status, notes, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (activity_id, checklist_id) DO UPDATE 
            SET status = EXCLUDED.status, notes = EXCLUDED.notes, created_by = EXCLUDED.created_by, updated_at = NOW()
            """,
            (activity_id, checklist_id, status, notes, user_id)
        )

def get_activity_checklist_results(activity_id: int) -> Dict[int, Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM monev_bos_checklist_results WHERE activity_id = %s", (activity_id,))
        return {row['checklist_id']: dict(row) for row in cur.fetchall()}

def add_audit_log(report_id: int, activity_id: Optional[int], user_id: int, action: str, details: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_audit_logs (report_id, activity_id, user_id, action, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (report_id, activity_id, user_id, action, details)
        )


# --- MASTER NAMA KEGIATAN ---
def list_master_activities(include_inactive: bool = False, fund_source: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        query = "SELECT * FROM monev_bos_master_activities WHERE 1=1"
        params: List[Any] = []
        if not include_inactive:
            query += " AND is_active = TRUE"
        if fund_source and fund_source != "ALL":
            query += " AND (fund_source = %s OR fund_source = 'ALL')"
            params.append(fund_source)
        query += " ORDER BY name ASC"
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

def create_master_activity(name: str, code_prefix: Optional[str] = None, fund_source: str = "ALL") -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO monev_bos_master_activities (name, code_prefix, fund_source)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET updated_at = NOW()
            RETURNING id
            """,
            (name.strip(), (code_prefix or "").strip() or None, fund_source)
        )
        return cur.fetchone()[0]

def update_master_activity(master_id: int, name: str, code_prefix: Optional[str], fund_source: str, is_active: bool) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE monev_bos_master_activities
            SET name = %s, code_prefix = %s, fund_source = %s, is_active = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (name.strip(), (code_prefix or "").strip() or None, fund_source, is_active, master_id)
        )

def delete_master_activity(master_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM monev_bos_master_activities WHERE id = %s", (master_id,))

def seed_default_master_activities() -> None:
    defaults = [
        ("Pemeliharaan Sarana & Alat Pelajaran Komputer", "01.02", "ALL"),
        ("Penyediaan Bahan Kebersihan & Kebutuhan Sanitasi", "01.03", "ALL"),
        ("Pembelian Alat Tulis Kantor", "01.01", "ALL"),
        ("Honorarium Guru Honorer / Tenaga Kependidikan", "02.01", "ALL"),
        ("Langganan Daya dan Jasa (Listrik/Air/Internet)", "03.01", "ALL"),
        ("Pemeliharaan Bangunan Sekolah & Ruang Kelas", "01.04", "ALL"),
        ("Pengadaan Modul & Bahan Ajar Siswa", "04.01", "ALL"),
        ("Kegiatan Asesmen & Evaluasi Pembelajaran", "05.01", "ALL"),
        ("Pengembangan Perpustakaan & Literasi", "06.01", "ALL"),
        ("Kegiatan Ekstrakurikuler & Lomba Siswa", "07.01", "ALL"),
    ]
    for name, code, fs in defaults:
        try:
            create_master_activity(name, code, fs)
        except Exception:
            pass

def get_audit_logs(report_id: int) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*, u.full_name as user_name, a.activity_name
            FROM monev_bos_audit_logs l
            JOIN dashboard_users u ON l.user_id = u.id
            LEFT JOIN monev_bos_activities a ON l.activity_id = a.id
            WHERE l.report_id = %s
            ORDER BY l.created_at DESC
            """,
            (report_id,)
        )
        return [dict(row) for row in cur.fetchall()]
