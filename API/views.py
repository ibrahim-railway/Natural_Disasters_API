from django.shortcuts import render
from django.http import JsonResponse
import requests
import math
from datetime import datetime
import json
import csv
from io import StringIO
import os 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
json_file = os.path.join(BASE_DIR, 'countries_coordinates.json')

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    R = 6371
    return R * c

def get_country_code_from_coordinates(lat, lon):
    # تحميل ملف الدول
    with open(json_file, 'r', encoding='utf-8') as f:
        countries = json.load(f)

    closest_country = None
    min_distance = float('inf')

    # مقارنة مع كل الدول
    for code, coords in countries.items():
        distance = haversine(lat, lon, coords['latitude'], coords['longitude'])
        if distance < min_distance:
            min_distance = distance
            closest_country = code

    return closest_country


# api 
api = {
    "usgs_er": 'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=NOW-1minute&limit=5&orderby=time',
    "usgs_vl": 'https://volcanoes.usgs.gov/hans-public/api/volcano/getCapElevated'
}

# Fake api
fake_api = {
    "usgs_er": "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=10"
}

# fakeم
fake_earthquakes_data = [
    {
        "properties": {
            "mag": 5.2,
            "time": datetime.utcnow().isoformat()
        },
        "geometry": {
            "coordinates": [30.82, 30.21, 10.7]
        }
    },
    {
        "properties": {
            "mag": 4.8,
            "time": datetime.utcnow().isoformat()
        },
        "geometry": {
            "coordinates": [31.02, 30.15, 12.1]
        }
    }
]

def get_volcanoes():
    try:
        res = requests.get(api['usgs_vl'])
        return res.json() if res.status_code == 200 else []
    except:
        return []

def get_fire(user_lat,user_lon):
    MAP_KEY = '6abb96f59f40a9614e4bf279a1c9b3bd'
    
    country_code = get_country_code_from_coordinates(user_lat, user_lon)
    print(f"Nearest country: {country_code}")
    
    # API URL for the last 7 days of fire data
    url = f'https://firms.modaps.eosdis.nasa.gov/api/country/csv/{MAP_KEY}/MODIS_NRT/{country_code}/1'
    data = requests.get(url)
    
    if data.status_code == 200:
        data2 = StringIO(data.text)
        reader = csv.DictReader(data2)

        for row in reader:
            fire_lat = float(row['latitude'])
            fire_lon = float(row['longitude'])
            distance = haversine(user_lat, user_lon, fire_lat, fire_lon)
            
            brightness = float(row['brightness'])
            frp = float(row['frp'])
            
            # Filtering for large fires based on brightness and FRP
            if distance <= 100 and brightness > 300 and frp > 50:
                return {
                    "Date":row['acq_date'],
                    "Time":row['acq_time'],
                    "Distance":distance,
                    "Coordinates":{"fire_lat":fire_lat,"fire_lon":fire_lon},
                    "Brightness":brightness,
                    "FRP":frp
                }
    else:
        return {"Error in API connection": data.status_code}


def get_hurricanes(lat, lon):
    api_key = 'c6f0033dd5cf5669fb07b1a9fcdc9c97'
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        weather_main = data['weather'][0]['main']
        description = data['weather'][0]['description']
        wind_speed = data['wind']['speed']
        pressure = data['main']['pressure']
        city_name = data.get("name", "Unknown")
        timestamp = datetime.utcfromtimestamp(data["dt"]).strftime('%Y-%m-%d %H:%M:%S')

        danger = weather_main in ['Thunderstorm', 'Tornado', 'Extreme'] or wind_speed > 20 or pressure < 1000

        if danger:
            return {
                "status": "DANGER",
                "city": city_name,
                "time_utc": timestamp,
                "weather_main": weather_main,
                "description": description,
                "wind_speed": wind_speed,
                "pressure": pressure
            }
        else:
            return {"status": "SAFE"}

    except Exception as e:
        return {"status": "UNKNOWN", "error": str(e)}

def index(request):

    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid or missing coordinates'}, status=400)

    use_fake = request.GET.get('fake', 'false') == 'true'

    is_in_egypt = 22 <= lat <= 32 and 25 <= lon <= 36
    earthquake_data = fake_earthquakes_data if use_fake and is_in_egypt else []

    if not earthquake_data:
        try:
            res = requests.get(api['usgs_er'])
            earthquake_data = res.json().get('features', [])
        except:
            earthquake_data = []

    earthquakes = []
    for quake in earthquake_data:
        try:
            mag = quake["properties"]["mag"]
            quake_lat = quake["geometry"]["coordinates"][1]
            quake_lon = quake["geometry"]["coordinates"][0]
            depth = quake["geometry"]["coordinates"][2]
            distance = haversine(quake_lat, quake_lon, lat, lon)
            impact = (mag ** 2) / ((distance + 1) * (depth / 10 + 1))

            if impact > 0.02:
                earthquakes.append({
                    "place": f"Near ({quake_lat}, {quake_lon})",
                    "magnitude": mag,
                    "depth_km": depth,
                    "distance_km": round(distance, 2),
                    "is_impactful": True,
                    "time": quake["properties"]["time"],
                    "source": "FAKE" if use_fake and is_in_egypt else "REAL"
                })
        except:
            continue

    volcano_data = []
    for v in get_volcanoes():
        try:
            vlat = v["latitude"]
            vlon = v["longitude"]
            dist = haversine(lat, lon, vlat, vlon)
            if dist < 500:
                volcano_data.append({
                    "name": v["volcano_name_appended"],
                    "distance_km": round(dist, 2),
                    "alert_level": v["alert_level"],
                    "color_code": v["color_code"],
                    "synopsis": v["synopsis"],
                    "source": "REAL"
                })
        except:
            continue

    return JsonResponse({
        "earthquake": earthquakes,
        "volcano": volcano_data,
        "hurricanes":get_hurricanes(lat,lon),
        "fire":get_fire(lat,lon)
    })

