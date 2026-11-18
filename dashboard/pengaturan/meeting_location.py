"""Validation shared by meeting setup and attendance geofencing."""
import math


def coordinates(latitude, longitude):
    try:
        lat, lng = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Titik lokasi wajib diisi dengan koordinat yang valid.") from None
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Koordinat lokasi tidak valid.")
    return lat, lng


def meeting_location(form):
    lat, lng = coordinates(form.get('latitude'), form.get('longitude'))
    try:
        radius = int(form.get('radius_m') or 200)
    except (TypeError, ValueError):
        raise ValueError("Radius harus berupa bilangan bulat dalam meter.") from None
    if not 1 <= radius <= 100000:
        raise ValueError("Radius harus antara 1 dan 100.000 meter.")
    return lat, lng, radius


def distance_m(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lng2-lng1)/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def validate_attendance_location(meeting, latitude, longitude):
    if meeting.get('latitude') is None or meeting.get('longitude') is None:
        raise ValueError("Titik lokasi meeting belum diatur. Edit meeting terlebih dahulu.")
    lat, lng = coordinates(latitude, longitude)
    distance = distance_m(lat, lng, float(meeting['latitude']), float(meeting['longitude']))
    radius = meeting.get('radius_m') or 200
    if distance > radius:
        raise ValueError(f"Di luar radius meeting: jarak {distance:.0f} meter, batas {radius} meter.")
    return lat, lng
