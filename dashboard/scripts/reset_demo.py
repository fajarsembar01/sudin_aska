import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from dashboard.db_access import get_cursor

NPSN = "20100677"


def reset_demo_school():
    print(f"Resetting data for school with NPSN {NPSN}...")
    with get_cursor(commit=True) as cur:
        # Find the school ID
        cur.execute("SELECT id, name FROM portal_schools WHERE npsn = %s", (NPSN,))
        school = cur.fetchone()

        if not school:
            print(
                f"School {NPSN} not found in portal_schools. Registration might fail if it relies on seeded data."
            )
            # Depending on logic, maybe we need to create it?
            # But the user implied "gunakan npsn ...", suggesting it exists or we use that one.
            # Usually these are seeded. If not, I should probably CREATE it now so the registration flow finds it.
            # But let's assume it exists or the user wants to reg for an existing one.
            # If not found, I'll log it.
            return

        school_id = school["id"]
        school_name = school["name"]
        print(f"Found School: {school_name} (ID: {school_id})")

        # Find users associated with this school
        cur.execute(
            "SELECT id, email, full_name FROM dashboard_users WHERE school_id = %s",
            (school_id,),
        )
        users = cur.fetchall()

        if users:
            print(f"Found {len(users)} users associated with this school:")
            for u in users:
                print(f" - Deleting User: {u['email']} ({u['full_name']})")

            # Delete them
            cur.execute(
                "DELETE FROM dashboard_users WHERE school_id = %s", (school_id,)
            )
            print("Users deleted.")
        else:
            print("No users found for this school. Ready for registration.")


if __name__ == "__main__":
    reset_demo_school()
