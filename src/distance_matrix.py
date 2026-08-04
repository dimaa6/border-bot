import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_KEY")

# Poland
origins_ua_pl = [
    {"latitude": 49.8445, "longitude": 24.0253},  # Lviv
    {"latitude": 50.7472, "longitude": 25.3254},  # Lutsk
    {"latitude": 51.2014, "longitude": 24.6773},  # Kovel
    {"latitude": 49.2486, "longitude": 23.8559},  # Stryi
    {"latitude": 50.09622, "longitude": 25.17622}  # Brody
]

destinations_ua_pl = [
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

# Slovakia
origins_ua_sk = [
    {"latitude": 49.8445, "longitude": 24.0253},  # Lviv
    {"latitude": 48.4597, "longitude": 22.7133},  # Mukachevo
    {"latitude": 48.5767, "longitude": 22.3363},  # Uzhhorod
]

destinations_ua_sk = [
    {"latitude": 48.86438, "longitude": 22.44406},  # Checkpoint Malyi Bereznyi
    {"latitude": 48.64744, "longitude": 22.26671},  # Checkpoint Uzhhorod
]

origins_sk = [
    {"latitude": 48.8992, "longitude": 22.3952},   # SK_Malyi Bereznyi
    {"latitude": 48.6549, "longitude": 22.2589},   # SK_Uzhhorod
]

destinations_sk = [
    {"latitude": 48.7304, "longitude": 21.4390},   # SK_Kocice
]

# Hungary
origins_ua_hu = [
    {"latitude": 48.4597, "longitude": 22.7133},  # Mukachevo
    {"latitude": 48.5767, "longitude": 22.3363},  # Uzhhorod
    {"latitude": 48.1769, "longitude": 23.2963},  # Khust
]

destinations_ua_hu = [
    {"latitude": 48.2549, "longitude": 22.45646},  # Checkpoint Kosyno
    {"latitude": 48.4280, "longitude": 22.1740},   # Checkpoint Chop
    {"latitude": 48.3127, "longitude": 22.33158},  # Checkpoint Dzvinkove
    {"latitude": 48.1681, "longitude": 22.58348},  # Checkpoint Luzhanka
    {"latitude": 48.1102, "longitude": 22.83615},  # Checkpoint Vylok
]

origins_hu = [
    {"latitude": 48.2318, "longitude": 22.43137},  # HU_Kosyno
    {"latitude": 48.3946, "longitude": 22.1655},   # HU_Chop
    {"latitude": 48.31726, "longitude": 22.2968},  # HU_Dzvinkove
    {"latitude": 48.1622, "longitude": 22.5638},   # HU_Luzhanka
    {"latitude": 48.0925, "longitude": 22.8211},   # HU_Vylok
]

destinations_hu = [
    {"latitude": 47.49734, "longitude": 19.0706},   # HU_Budapest
]

# Romania
origins_ua_ro = [
    {"latitude": 48.4597, "longitude": 22.7133},  # Mukachevo
    {"latitude": 48.9213, "longitude": 24.7073},  # Ivano-Frankivsk
    {"latitude": 48.2920, "longitude": 25.9353},  # Chernivtsi
    {"latitude": 46.5029, "longitude": 30.61084}, # Odesa
]

destinations_ua_ro = [
    {"latitude": 45.3124, "longitude": 28.4462},  # Checkpoint Orlivka
    {"latitude": 48.10767, "longitude": 26.2809}, # Checkpoint Dyakivtsi
    {"latitude": 48.0062, "longitude": 23.0018},  # Checkpoint Dyakove
    {"latitude": 47.9531, "longitude": 25.62044}, # Checkpoint Krasnoilsk
    {"latitude": 47.9960, "longitude": 26.0535},  # Checkpoint Porubne
    {"latitude": 47.94204, "longitude": 23.8766}, # Checkpoint Solotvyno
]

origins_ro = [
    {"latitude": 45.2769, "longitude": 28.4555},  # RO_Orlivka
    {"latitude": 48.09759, "longitude": 26.2836}, # RO_Dyakivtsi
    {"latitude": 47.9932, "longitude": 23.0028},  # RO_Dyakove
    {"latitude": 47.9438, "longitude": 25.6238},  # RO_Krasnoilsk
    {"latitude": 47.9833, "longitude": 26.0631},  # RO_Porubne
    {"latitude": 47.93843, "longitude": 23.8775}, # RO_Solotvyno
]

destinations_ro = [
    {"latitude": 44.4363, "longitude": 26.1019},  # RO_Bucharest
    {"latitude": 44.2628, "longitude": 28.5538},  # RO_Constanta
]

# Moldova

origins_ua_md = [
    {"latitude": 49.2442, "longitude": 28.4774},  # Vinnytsia
    {"latitude": 48.7258, "longitude": 30.2544},  # Uman
    {"latitude": 46.5029, "longitude": 30.61084}, # Odesa
]

destinations_ua_md = [
    {"latitude": 48.4543, "longitude": 27.7784},  # Checkpoint Mohyliv-Podilskyi
    {"latitude": 48.40045, "longitude": 27.8801}, # Checkpoint Bronnytsya
    {"latitude": 48.3919, "longitude": 27.01586}, # Checkpoint Rososhany
    {"latitude": 48.25795, "longitude": 26.5940}, # Checkpoint Mamalyha
    {"latitude": 48.4403, "longitude": 27.4449},  # Checkpoint Sokyryany
    {"latitude": 46.3787, "longitude": 30.0854},  # Checkpoint Mayaky-Udobne
]

origins_md = [
    {"latitude": 48.4436, "longitude": 27.7844},  # MD_Mohyliv-Podilskyi
    {"latitude": 48.3980, "longitude": 27.8749},  # MD_Bronnytsya
    {"latitude": 48.3676, "longitude": 27.0648},  # MD_Rososhany
    {"latitude": 48.2673, "longitude": 26.6483},  # MD_Mamalyha
    {"latitude": 48.4202, "longitude": 27.4545},  # MD_Sokyryany
    {"latitude": 46.4118, "longitude": 30.1010},  # MD_Mayaky-Udobne
]

destinations_md = [
    {"latitude": 47.0351, "longitude": 28.84745}, # MD_Kishinev
]

origins = origins_md
destinations = destinations_md

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