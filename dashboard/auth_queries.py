
from typing import Optional
from dashboard.db_access import get_cursor

def create_pending_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str = "staff",
    whatsapp: Optional[str] = None,
    nip: Optional[str] = None,
    nrk: Optional[str] = None,
    jabatan: Optional[str] = None,
    kecamatan_id: Optional[int] = None
) -> int:
    """Create a new user with pending status."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO dashboard_users (
                email, full_name, password_hash, role, 
                whatsapp_number, nip, nrk, jabatan, 
                requested_kecamatan, account_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (email, full_name, password_hash, role, whatsapp, nip, nrk, jabatan, kecamatan_id)
        )
        new_id = cur.fetchone()[0]
        
        # Determine admin user for assignment based on kecamatan if possible
        # For now, just leave user_kecamatan empty until approved
        
    return int(new_id)
