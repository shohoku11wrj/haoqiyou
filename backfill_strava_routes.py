from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
import datetime
import os
import pytz
import requests

# Load environment variables from .env file
load_dotenv()

# MongoDB connection setup
MONGO_CONNECTION_STRING = os.getenv('MONGO_CONNECTION_STRING')
RIDE_EVENT_DB_NAME = os.getenv('RIDE_EVENT_DB_NAME')
RIDE_EVENTS_COLLECTION_NAME = os.getenv('RIDE_EVENTS_CITY_COLLECTION_NAME')
client = MongoClient(MONGO_CONNECTION_STRING)
db = client[RIDE_EVENT_DB_NAME]
collection = db[RIDE_EVENTS_COLLECTION_NAME]

# Google Maps API
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

# Strava API AccessToken
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
STRAVA_REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')
access_token = None

def refresh_access_token(client_id, client_secret, refresh_token):
    url = 'https://www.strava.com/oauth/token'
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        token_info = response.json()
        return token_info['access_token'], token_info['refresh_token']
    else:
        response.raise_for_status()

# Refresh the access token
access_token, refresh_token = refresh_access_token(
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
)

# 获取当前时间所在周的周一00:00AM时间
def get_start_of_week():
    now = datetime.datetime.now(pytz.utc)  # 使用UTC时间
    start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    return start_of_week

def get_route_details(route_id, access_token):
    if route_id is None or route_id == "":
        return {}
    url = f"https://www.strava.com/api/v3/routes/{route_id}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()


##########################################################################
# Backfill strava_routes that are active and after the start of the week #
##########################################################################
start_of_week_utc = get_start_of_week()
strava_routes_cursor = collection.find({
    'is_active': True,
    '$or': [
        {'event_time_utc': {'$gte': start_of_week_utc}},
        {'event_time_utc': {'$type': 'string', '$gte': start_of_week_utc.isoformat()}}
    ],
    'source_type': {'$ne': 'strava'},
    'strava_url': {'$exists': 1},
    '$or': [
        {'is_backfilled': {'$exists': False}},
        {'is_backfilled': {'$eq': False}}
    ]
})
backfill_event_count = 0
# Create a list of UpdateOne operations for MongoDB
operations = []


for strava_route_event in strava_routes_cursor:
    backfill_event_count += 1
    try:
        # extract the route_id from the strava_url https://www.strava.com/routes/3257233396236180976
        strava_route_id = int(strava_route_event['strava_url'].split('/')[-1])
        route_details = get_route_details(strava_route_id, access_token)
        distance = route_details.get('distance', None)  # Distance in meters
        elevation_gain = route_details.get('elevation_gain', None)  # Elevation gain in meters
        distance_meters = int(distance)
        elevation_gain_meters = int(elevation_gain)
        strava_map_url = route_details.get('map_urls', {}).get('url', None)
        route_polyline = route_details.get('map', {}).get('summary_polyline', '')
    except ValueError as e:
        print(e)
    
    # Prepare the event document for MongoDB
    update_event_document = {
        'distance_meters': distance_meters,
        'elevation_gain_meters': elevation_gain_meters,
        'route_map_url': strava_map_url,
        'route_polyline': route_polyline,
        'raw_event': route_details,
        'is_backfilled': True
    }

    operations.append(
        UpdateOne(
            {
                'source_type': strava_route_event['source_type'],
                'source_group_id': strava_route_event['source_group_id'],
                'source_event_id': strava_route_event['source_event_id']
            },
            {'$set': update_event_document}
        )
    )

print(f"Backfilled {backfill_event_count} strava_routes")

# Execute the bulk write operation
if operations:
    result = collection.bulk_write(operations)
    print(f"Bulk write result: {result.bulk_api_result}")