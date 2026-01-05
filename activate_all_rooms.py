"""Script to activate all rooms and aspects in the portal."""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard.db_access import get_cursor

def activate_all():
    """Set all rooms and aspects to active=true."""
    with get_cursor(commit=True) as cur:
        # Activate all rooms
        cur.execute("UPDATE portal_rooms SET active = true WHERE active = false;")
        rooms_updated = cur.rowcount
        print(f"✅ Updated {rooms_updated} rooms to active")
        
        # Activate all aspects
        cur.execute("UPDATE portal_aspects SET active = true WHERE active = false;")
        aspects_updated = cur.rowcount
        print(f"✅ Updated {aspects_updated} aspects to active")
        
    print("Done!")

if __name__ == "__main__":
    activate_all()
