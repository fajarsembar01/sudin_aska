import random
from dashboard import create_app
from dashboard.db_access import get_cursor

app = create_app()

def generate_dummy():
    with app.app_context():
        with get_cursor(commit=True) as cur:
            # 0. Get Admin/Staff ID
            cur.execute("SELECT id FROM dashboard_users WHERE role = 'admin' LIMIT 1")
            admin = cur.fetchone()
            if not admin:
                print("Error: No admin user found to assign as assessor.")
                # Fallback: create one? Assuming at least one admin exists from setup.
                return
            staff_id = admin['id']

            # 1. Get Active/Latest Period
            cur.execute("SELECT id FROM portal_assessment_periods WHERE is_active = TRUE LIMIT 1")
            period = cur.fetchone()
            if not period:
                cur.execute("""
                    INSERT INTO portal_assessment_periods (name, start_date, end_date, is_active)
                    VALUES ('Periode Percobaan 2024', NOW(), NOW() + INTERVAL '30 days', TRUE)
                    RETURNING id
                """)
                period_id = cur.fetchone()['id']
            else:
                period_id = period['id']
                
            # 1.5 Get Master Room (Ruang Kelas)
            cur.execute("SELECT id FROM portal_rooms LIMIT 1")
            master_room = cur.fetchone()
            if not master_room:
                 cur.execute("INSERT INTO portal_rooms (name, category) VALUES ('Ruang Kelas', 'Utama') RETURNING id")
                 master_room_id = cur.fetchone()['id']
            else:
                 master_room_id = master_room['id']

            # 2. Get Public Schools
            cur.execute("SELECT id, name FROM portal_schools WHERE status = 'NEGERI'")
            schools = cur.fetchall()
            print(f"Found {len(schools)} public schools.")
            
            count = 0
            photo_count = 0
            
            for s in schools:
                if random.random() > 0.8: continue
                    
                status = random.choice(['draft', 'submitted', 'verified', 'verified', 'submitted'])
                score = round(random.uniform(1.5, 3.0), 2)
                
                # Check exist
                cur.execute("SELECT id FROM portal_assessments WHERE school_id = %s AND period_id = %s", (s['id'], period_id))
                existing = cur.fetchone()
                
                if existing:
                    cur.execute("""
                        UPDATE portal_assessments 
                        SET status = %s, total_score = %s, submitted_at = CASE WHEN %s != 'draft' THEN NOW() ELSE NULL END, updated_at = NOW()
                        WHERE id = %s
                        RETURNING id
                    """, (status, score, status, existing['id']))
                    assessment_id = existing['id']
                else:
                    cur.execute("""
                        INSERT INTO portal_assessments (school_id, period_id, staff_id, status, total_score, created_at, updated_at, submitted_at)
                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), CASE WHEN %s != 'draft' THEN NOW() ELSE NULL END)
                        RETURNING id
                    """, (s['id'], period_id, staff_id, status, score, status))
                    assessment_id = cur.fetchone()['id']
                
                count += 1
                
                # Insert Dummy Photo (Only for non-draft)
                if status != 'draft':
                    # Ensure School has Room
                    cur.execute("SELECT id FROM portal_school_rooms WHERE school_id = %s AND room_id = %s", (s['id'], master_room_id))
                    s_room = cur.fetchone()
                    if s_room:
                        room_id = s_room['id']
                    else:
                        cur.execute("INSERT INTO portal_school_rooms (school_id, room_id, quantity) VALUES (%s, %s, 1) RETURNING id", (s['id'], master_room_id))
                        room_id = cur.fetchone()['id']
                        
                    lat = random.uniform(-6.30, -6.15)
                    lng = random.uniform(106.75, 106.90)
                    
                    # Insert Photo
                    cur.execute("""
                        INSERT INTO portal_assessment_photos (assessment_id, school_room_id, photo_path, latitude, longitude, created_at)
                        VALUES (%s, %s, 'https://placehold.co/600x400?text=Lokasi', %s, %s, NOW())
                        ON CONFLICT (assessment_id, school_room_id) DO UPDATE 
                        SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """, (assessment_id, room_id, lat, lng))
                    photo_count += 1
                
            print(f"Processed {count} assessments, created {photo_count} photos.")

if __name__ == '__main__':
    generate_dummy()
