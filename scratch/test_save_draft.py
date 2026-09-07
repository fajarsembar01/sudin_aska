import os
import sys

# Add project root to python path
sys.path.insert(
    0,
    r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2",
)

from dashboard.laporan.queries import (
    create_form,
    delete_form,
    get_form_fields,
    replace_form_fields,
)

try:
    print("Testing replace_form_fields with new types...")
    # Create a temporary draft form
    form = create_form(
        title="Temporary Test Form",
        description="Testing save draft constraint",
        target_scope="all",
        target_jenjang=None,
        allow_multiple=False,
        allow_late=False,
        very_late_after_minutes=180,
        no_submission_after_minutes=None,
        no_submission_jenjangs=None,
        no_submission_statuses=None,
        is_active=False,
        deadline_at=None,
        created_by=1,  # assuming admin user id 1 exists
        status="draft",
        repeat_policy="once",
        repeat_until_at=None,
        repeat_deadline_time=None,
        repeat_deadline_day=None,
    )
    form_id = form["id"]
    print(f"Created temporary form with ID: {form_id}")

    test_fields = [
        {
            "field_key": "test_doc_field",
            "label": "Unggah Dokumen Laporan",
            "field_type": "upload_dokumen",
            "options_json": None,
            "required": True,
            "sort_order": 0,
        },
        {
            "field_key": "test_img_field",
            "label": "Unggah Foto Kegiatan",
            "field_type": "upload_gambar",
            "options_json": None,
            "required": False,
            "sort_order": 1,
        },
    ]

    # Try replacing/saving fields
    replace_form_fields(form_id, test_fields)
    print("replace_form_fields called successfully without database errors!")

    # Retrieve to confirm
    saved_fields = get_form_fields(form_id)
    print("Saved fields retrieved:")
    for f in saved_fields:
        print(
            f" - ID: {f['id']}, Key: {f['field_key']}, Type: {f['field_type']}, Label: {f['label']}"
        )

    # Clean up
    delete_form(form_id)
    print("Temporary form deleted.")
    print("VERIFICATION SUCCESSFUL!")

except Exception as e:
    print(f"Verification failed: {e}")
