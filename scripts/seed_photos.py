"""
Script to insert sample school room photos into the database.
This populates the gallery with real AI-generated images.
"""
import random
from dashboard import create_app
from dashboard.db_access import get_cursor

app = create_app()

# Sample photos from AI generation
SAMPLE_PHOTOS = [
    "classroom_sample_1_1765337156962.png",
    "school_hallway_1_1765337195854.png",
    "school_toilet_1_1765337213676.png",
    "school_library_1_1765337233210.png",
    "school_canteen_1_1765337251722.png",
    "school_gate_1_1765337270090.png",
]


def seed_photos():
    with app.app_context():
        with get_cursor(commit=True) as cur:
            # Get assessments that are submitted or verified
            cur.execute("""
                SELECT a.id as assessment_id, a.school_id, sr.id as school_room_id
                FROM portal_assessments a
                JOIN portal_school_rooms sr ON sr.school_id = a.school_id
                WHERE a.status IN ('submitted', 'verified')
                ORDER BY a.id, sr.id
            """)
            records = cur.fetchall()
            
            if not records:
                print("No submitted/verified assessments found. Run `python -m scripts.seed_dummy` first.")
                return
            
            print(f"Found {len(records)} assessment-room combinations")
            
            photo_count = 0
            score_count = 0
            
            for rec in records:
                # Random photo from samples
                photo_file = random.choice(SAMPLE_PHOTOS)
                photo_path = f"uploads/portal/{photo_file}"
                
                # Random GPS coordinates in Jakarta Utara area
                lat = round(random.uniform(-6.30, -6.10), 6)
                lng = round(random.uniform(106.75, 106.95), 6)
                
                # Upsert photo
                cur.execute("""
                    INSERT INTO portal_assessment_photos 
                        (assessment_id, school_room_id, photo_path, latitude, longitude, captured_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW() - INTERVAL '%s days', NOW())
                    ON CONFLICT (assessment_id, school_room_id) 
                    DO UPDATE SET 
                        photo_path = EXCLUDED.photo_path,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        captured_at = EXCLUDED.captured_at,
                        created_at = NOW()
                """, (
                    rec['assessment_id'], 
                    rec['school_room_id'], 
                    photo_path, 
                    lat, 
                    lng,
                    random.randint(0, 30)  # Random capture date within last 30 days
                ))
                photo_count += 1
                
                # Get aspects for this room
                cur.execute("""
                    SELECT pa.id as aspect_id 
                    FROM portal_aspects pa
                    JOIN portal_school_rooms sr ON sr.room_id = pa.room_id
                    WHERE sr.id = %s
                """, (rec['school_room_id'],))
                aspects = cur.fetchall()
                
                # Insert random scores for each aspect
                for aspect in aspects:
                    score = random.choice([1, 2, 2, 3, 3, 3])  # Skewed towards higher scores
                    cur.execute("""
                        INSERT INTO portal_assessment_scores 
                            (assessment_id, school_room_id, aspect_id, score, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (assessment_id, school_room_id, aspect_id)
                        DO UPDATE SET score = EXCLUDED.score, updated_at = NOW()
                    """, (rec['assessment_id'], rec['school_room_id'], aspect['aspect_id'], score))
                    score_count += 1
            
            print(f"Successfully inserted/updated {photo_count} photos and {score_count} scores!")


if __name__ == '__main__':
    seed_photos()
