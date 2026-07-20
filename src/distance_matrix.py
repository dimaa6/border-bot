import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_KEY")

# Define your 4 origins and 4 destinations (lat, lng or address strings)
origins_ua = [
    {"latitude": 49.8445, "longitude": 24.0253},  # Lviv
    {"latitude": 50.7472, "longitude": 25.3254},  # Lutsk
    {"latitude": 51.2014, "longitude": 24.6773},  # Kovel
    {"latitude": 49.2486, "longitude": 23.8559},  # Stryi
]

destinations_ua = [
    {"latitude": 50.86069, "longitude": 24.15097},  # Checkpoint Ustyluh
    {"latitude": 49.94905, "longitude": 23.15331},  # Checkpoint Krakivets
    {"latitude": 50.25847, "longitude": 23.60417},  # Checkpoint Rava-Ruska
    {"latitude": 49.79894, "longitude": 23.00721},  # Checkpoint Shehyni
    {"latitude": 50.56388, "longitude": 24.11818},  # Checkpoint Uhryniv
    {"latitude": 50.08358, "longitude": 23.3108},   # Checkpoint Hrushiv
    {"latitude": 49.67952, "longitude": 22.81162},  # Checkpoint Nizhankovichi
    {"latitude": 49.4803, "longitude": 22.73878},   # Checkpoint Smilnytsia
]

origins_pl = [
    {"latitude": 50.8595, "longitude": 24.12974},   # PL_Ustyluh
    {"latitude": 49.95718, "longitude": 23.10973},  # PL_Krakivets
    {"latitude": 50.28533, "longitude": 23.5727},   # PL_Rava-Ruska
    {"latitude": 49.79376, "longitude": 22.9103},   # PL_Shehyni
    {"latitude": 50.58313, "longitude": 24.05494},  # PL_Uhryniv
    {"latitude": 50.1021, "longitude": 23.2571},    # PL_Hrushiv
    {"latitude": 49.71538, "longitude": 22.8206},   # PL_Nizhankovichi
    {"latitude": 49.4779, "longitude": 22.6682},    # PL_Smilnytsia
]

destinations_pl = [
    {"latitude": 50.05027, "longitude": 19.95215},  # Krakow
    {"latitude": 52.2286, "longitude": 21.00046},   # Warsaw
]

origins = origins_ua
destinations = destinations_ua

def fetch_duration_matrix():
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        # Request ONLY the duration field to keep payload light
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,status",
    }

    payload = {
        "origins": [
            {"waypoint": {"location": {"latLng": o}}} for o in origins
        ],
        "destinations": [
            {"waypoint": {"location": {"latLng": d}}} for d in destinations
        ],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",  # Ensures clean, static travel time without live traffic noise
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        results = json.loads(response.read().decode('utf-8'))

    matrix = [[0 for _ in range(len(destinations))] for _ in range(len(origins))]

    for entry in results:
        o_idx = entry.get("originIndex", 0)
        d_idx = entry.get("destinationIndex", 0)

        # Duration is returned as a string like "12450s"
        duration_str = entry.get("duration", "0s")
        seconds = int(duration_str.rstrip("s"))
        minutes = round(seconds / 60)

        matrix[o_idx][d_idx] = minutes

    return matrix


# Execute and print
matrix_in_minutes = fetch_duration_matrix()
print("Static Driving Time Matrix (in minutes):")
for row in matrix_in_minutes:
    print(row)