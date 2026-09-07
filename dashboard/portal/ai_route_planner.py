"""AI Route Planner for Sidak (School Inspection).

This module provides AI-powered route optimization for efficient school inspections.
Uses Groq (Llama) for analyzing GPS coordinates and suggesting optimal visiting order.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

# Default starting point: Kantor Walikota Jakarta Utara
# Jl. Laksda Yos Sudarso No. 27-29, Tanjung Priok
DEFAULT_START_LOCATION = {
    "name": "Kantor Walikota Jakarta Utara",
    "latitude": -6.1203950,
    "longitude": 106.8920090,
}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates in kilometers."""
    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def nearest_neighbor_route(
    schools: List[Dict[str, Any]],
    start_lat: float,
    start_lon: float,
) -> List[Dict[str, Any]]:
    """
    Simple nearest neighbor algorithm for route optimization.
    Fallback when AI is not available.
    """
    if not schools:
        return []

    remaining = list(schools)
    ordered = []
    current_lat, current_lon = start_lat, start_lon

    while remaining:
        # Find nearest school
        nearest_idx = 0
        nearest_dist = float("inf")

        for i, school in enumerate(remaining):
            if school.get("latitude") and school.get("longitude"):
                dist = haversine_distance(
                    current_lat, current_lon, school["latitude"], school["longitude"]
                )
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_idx = i

        # Move to nearest school
        nearest = remaining.pop(nearest_idx)
        ordered.append(nearest)
        if nearest.get("latitude") and nearest.get("longitude"):
            current_lat = nearest["latitude"]
            current_lon = nearest["longitude"]

    return ordered


def optimize_route(
    schools: List[Dict[str, Any]],
    start_lat: float = DEFAULT_START_LOCATION["latitude"],
    start_lon: float = DEFAULT_START_LOCATION["longitude"],
) -> List[Dict[str, Any]]:
    """
    Optimize visiting order using nearest neighbor algorithm.
    Simple, reliable, and fast - no AI dependency.
    """
    if len(schools) <= 1:
        return schools

    return nearest_neighbor_route(schools, start_lat, start_lon)


def generate_gmaps_deeplink(
    schools: List[Dict[str, Any]],
    start_lat: float = DEFAULT_START_LOCATION["latitude"],
    start_lon: float = DEFAULT_START_LOCATION["longitude"],
) -> str:
    """
    Generate Google Maps deep link for navigation.
    Free - no API key required.
    """
    if not schools:
        return ""

    # Filter schools with valid GPS
    valid_schools = [s for s in schools if s.get("latitude") and s.get("longitude")]
    if not valid_schools:
        return ""

    # Origin is start location
    origin = f"{start_lat},{start_lon}"

    # Last school is destination
    last = valid_schools[-1]
    destination = f"{last['latitude']},{last['longitude']}"

    # All other schools are waypoints
    waypoints = []
    for s in valid_schools[:-1]:
        waypoints.append(f"{s['latitude']},{s['longitude']}")

    # Build URL
    base_url = "https://www.google.com/maps/dir/?api=1"
    parts = [
        f"origin={origin}",
        f"destination={destination}",
        "travelmode=driving",
    ]

    if waypoints:
        parts.append(f"waypoints={quote_plus('|'.join(waypoints))}")

    return f"{base_url}&{'&'.join(parts)}"


def calculate_route_stats(
    schools: List[Dict[str, Any]],
    start_lat: float = DEFAULT_START_LOCATION["latitude"],
    start_lon: float = DEFAULT_START_LOCATION["longitude"],
) -> Dict[str, Any]:
    """Calculate estimated distance and time for route."""
    if not schools:
        return {"distance_km": 0, "estimated_minutes": 0}

    total_distance = 0
    current_lat, current_lon = start_lat, start_lon

    for school in schools:
        if school.get("latitude") and school.get("longitude"):
            total_distance += haversine_distance(
                current_lat, current_lon, school["latitude"], school["longitude"]
            )
            current_lat = school["latitude"]
            current_lon = school["longitude"]

    # Estimate time: 30 km/h average speed in city + 10 min per school
    avg_speed = 30  # km/h
    visit_time_per_school = 10  # minutes

    travel_time = (total_distance / avg_speed) * 60  # minutes
    total_time = travel_time + (len(schools) * visit_time_per_school)

    return {
        "distance_km": round(total_distance, 1),
        "travel_minutes": round(travel_time),
        "total_minutes": round(total_time),
        "school_count": len(schools),
    }
