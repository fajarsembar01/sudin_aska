"""
Create dummy coordinator and staff data for Tim Monev testing.
Run: python3 create_dummy_team_data.py
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

# Database connection
conn_args = dict(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
)

# Dummy users data
DUMMY_USERS = [
    # Koordinator Kasi
    {"email": "kasi.sd@test.com", "name": "Mulyadi (Kasi SD)", "role": "coordinator", "jabatan": "Kepala Seksi SD", "nip": "198501012010011001"},
    {"email": "kasi.smp@test.com", "name": "Acep Mahmudin (Kasi SMP SMA)", "role": "coordinator", "jabatan": "Kepala Seksi SMP SMA", "nip": "198502022010011002"},
    {"email": "kasi.paud@test.com", "name": "Meliyati (Kasi PAUD)", "role": "coordinator", "jabatan": "Kepala Seksi PAUD PMPK", "nip": "198503032010011003"},
    {"email": "kasi.smk@test.com", "name": "Suyamti (Kasi SMK)", "role": "coordinator", "jabatan": "Kepala Seksi SMK KP", "nip": "198504042010011004"},
    
    # Koordinator Kecamatan (Kasatlak)
    {"email": "kasatlak.cilincing@test.com", "name": "Sahri (Kasatlak Cilincing)", "role": "coordinator", "jabatan": "Kasatlak Dikcam Cilincing", "nip": "198601012010011005"},
    {"email": "kasatlak.koja@test.com", "name": "Jumaedy (Kasatlak Koja)", "role": "coordinator", "jabatan": "Plt. Kasatlak Dikcam Koja", "nip": "198602022010011006"},
    {"email": "kasatlak.kgading@test.com", "name": "Sriyono (Kasatlak K.Gading)", "role": "coordinator", "jabatan": "Kasatlak Dikcam Kelapa Gading", "nip": "198603032010011007"},
    
    # Staff
    {"email": "staff.sd1@test.com", "name": "Richi Fernando (Staff SD)", "role": "staff", "jabatan": "Staf Seksi SD", "nip": "199001012015011001"},
    {"email": "staff.sd2@test.com", "name": "Ade Budiman (Staff SD)", "role": "staff", "jabatan": "Staf Seksi SD", "nip": "199002022015011002"},
    {"email": "staff.smp1@test.com", "name": "July Astuti (Staff SMP)", "role": "staff", "jabatan": "Staf Seksi SMP SMA", "nip": "199003032015011003"},
    {"email": "staff.cilincing1@test.com", "name": "Ahmad Turmuzi (Staff Cilincing)", "role": "staff", "jabatan": "Staf Satlak Cilincing", "nip": "199004042015011004"},
    {"email": "staff.koja1@test.com", "name": "Anton Purbaya (Staff Koja)", "role": "staff", "jabatan": "Staf Satlak Koja", "nip": "199005052015011005"},
]

PASSWORD = "testing123"

def create_dummy_users():
    print("🚀 Creating dummy users for Tim Monev testing...")
    
    conn = psycopg2.connect(**conn_args)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    created_users = []
    
    try:
        hashed_password = generate_password_hash(PASSWORD, method='pbkdf2:sha256')
        
        for user in DUMMY_USERS:
            # Check if user exists
            cur.execute("SELECT id FROM dashboard_users WHERE email = %s", (user["email"],))
            existing = cur.fetchone()
            
            if existing:
                print(f"  ⏭️ User {user['email']} already exists (ID: {existing['id']})")
                created_users.append({"id": existing['id'], **user})
            else:
                cur.execute("""
                    INSERT INTO dashboard_users (email, password_hash, full_name, role, jabatan, nip, account_status, created_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, 'approved', NOW())
                    RETURNING id
                """, (user["email"], hashed_password, user["name"], user["role"], user["jabatan"], user["nip"]))
                row = cur.fetchone()
                print(f"  ✅ Created user: {user['name']} ({user['email']}) - ID: {row['id']}")
                created_users.append({"id": row['id'], **user})
        
        conn.commit()
        print(f"\n✅ {len(created_users)} users ready!")
        
        # Now assign coordinators to teams
        print("\n🔗 Assigning coordinators to teams...")
        
        # Get teams
        cur.execute("SELECT id, name, team_type FROM monev_teams ORDER BY team_type, name")
        teams = cur.fetchall()
        
        # Mapping
        coordinator_mapping = {
            "SD": "kasi.sd@test.com",
            "SMP SMA": "kasi.smp@test.com",
            "PAUD PMPK": "kasi.paud@test.com",
            "SMK, Kursus & Pelatihan": "kasi.smk@test.com",
            "Tim Monev CILINCING": "kasatlak.cilincing@test.com",
            "Tim Monev KOJA": "kasatlak.koja@test.com",
            "Tim Monev KELAPA GADING": "kasatlak.kgading@test.com",
        }
        
        for team in teams:
            team_name = team['name']
            if team_name in coordinator_mapping:
                coord_email = coordinator_mapping[team_name]
                coord_user = next((u for u in created_users if u['email'] == coord_email), None)
                if coord_user:
                    cur.execute("UPDATE monev_teams SET coordinator_id = %s WHERE id = %s", (coord_user['id'], team['id']))
                    print(f"  ✅ Assigned {coord_user['name']} as coordinator for {team_name}")
        
        conn.commit()
        
        # Add some team members
        print("\n👥 Adding team members...")
        
        member_mapping = {
            "SD": ["staff.sd1@test.com", "staff.sd2@test.com"],
            "SMP SMA": ["staff.smp1@test.com"],
            "Tim Monev CILINCING": ["staff.cilincing1@test.com"],
            "Tim Monev KOJA": ["staff.koja1@test.com"],
        }
        
        for team in teams:
            team_name = team['name']
            if team_name in member_mapping:
                for member_email in member_mapping[team_name]:
                    member_user = next((u for u in created_users if u['email'] == member_email), None)
                    if member_user:
                        # Check if already member
                        cur.execute("SELECT id FROM monev_team_members WHERE team_id = %s AND staff_id = %s", 
                                    (team['id'], member_user['id']))
                        if not cur.fetchone():
                            cur.execute("""
                                INSERT INTO monev_team_members (team_id, staff_id, added_at) 
                                VALUES (%s, %s, NOW())
                            """, (team['id'], member_user['id']))
                            print(f"  ✅ Added {member_user['name']} to {team_name}")
                        else:
                            print(f"  ⏭️ {member_user['name']} already in {team_name}")
        
        conn.commit()
        print("\n🎉 All dummy data created successfully!")
        
        # Print summary
        print("\n" + "="*60)
        print("📋 CREDENTIAL SUMMARY")
        print("="*60)
        print(f"Password for all accounts: {PASSWORD}")
        print("\nKoordinator Kasi:")
        for u in created_users:
            if u['role'] == 'coordinator' and 'kasi' in u['email']:
                print(f"  • {u['email']}")
        
        print("\nKoordinator Kecamatan:")
        for u in created_users:
            if u['role'] == 'coordinator' and 'kasatlak' in u['email']:
                print(f"  • {u['email']}")
        
        print("\nStaff:")
        for u in created_users:
            if u['role'] == 'staff':
                print(f"  • {u['email']}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    create_dummy_users()
