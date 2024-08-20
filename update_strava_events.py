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


# 从以下Strava Clubs中获取Events
club_ids = [
    '1263183',  # Thunder Bluff Leisure Cycling Club 雷霆崖骑行观光团
    '195196',   # 山神廟
    '1157973',  # Featherweight Club (FWC)
    '265',      # Los Gatos Bicycle Racing Club
    '1047313',  # Alto Velo C Ride
    '1115522',  # NorCal Cycling China Fans
    '908336'    # Ruekn Bicci Gruppo (Southern California)
]

# Strava APIs

def get_club_events(club_id, access_token):
    url = f'https://www.strava.com/api/v3/clubs/{club_id}/group_events'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        return None

def get_route_details(route_id, access_token):
    url = f"https://www.strava.com/api/v3/routes/{route_id}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def get_event_route_distance_and_elevation(route_id, access_token):
    route_details = get_route_details(route_id, access_token)
    distance = route_details.get('distance', None)  # Distance in meters
    elevation_gain = route_details.get('elevation_gain', None)  # Elevation gain in meters
    return distance, elevation_gain

# 获取当前时间所在周的周一00:00AM时间
def get_start_of_week():
    now = datetime.datetime.now(pytz.utc)  # 使用UTC时间
    start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    return start_of_week

start_of_week = get_start_of_week()

# 创建一个字典来存储每个俱乐部的事件数据
all_events = {}
for club_id in club_ids:
    events = get_club_events(club_id, access_token)
    if events:
        # 过滤仅包括本周开始后的活动
        filtered_events = []
        for event in events:
            if 'upcoming_occurrences' in event:
                occurrences = event['upcoming_occurrences']
                valid_occurrences = [occurrence for occurrence in occurrences if datetime.datetime.strptime(occurrence, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc) > start_of_week]
                if valid_occurrences:
                    event['upcoming_occurrences'] = valid_occurrences
                    filtered_events.append(event)
        all_events[club_id] = filtered_events

# Use a dictionary to deduplicate events by (club_id, event_id)
deduped_events = {}
for club_id, events in all_events.items():
    for event in events:
        event_key = (club_id, event['id'])
        deduped_events[event_key] = event

# Convert deduplicated events back to a list
all_events_list = [(club_id, event_id, event) for (club_id, event_id), event in deduped_events.items()]

# DEBUG: 在CLI中打印events的数量
print(f"Total number of duduped_events: {len(all_events_list)}")

all_events_list = []  # List of all events by (club_id, event_id, event) tuple
for club_id, events in all_events.items():
    for event in events:
        all_events_list.append((club_id, event['id'], event))
# Sort the events by their start time
all_events_list.sort(key=lambda x: datetime.datetime.strptime(x[2]['upcoming_occurrences'][0], '%Y-%m-%dT%H:%M:%SZ'))
# Create a list of UpdateOne operations
operations = []

for club_id, event_id, event in all_events_list:
    club_name = event['club']['name']
    event_time_utc = datetime.datetime.strptime(event['upcoming_occurrences'][0], '%Y-%m-%dT%H:%M:%SZ')
    event_time_utc = event_time_utc.replace(tzinfo=pytz.utc)
    # Format the GPS coordinates to at most 5 digits after floats, and without brackets
    gps_coordinates = ', '.join(map(str, [round(coord, 5) for coord in event['start_latlng']])) if event['start_latlng'] else ''
    # Check if organizing_athlete is not None
    if event['organizing_athlete'] is not None:
        organizer = f"{event['organizing_athlete']['firstname']} {event['organizing_athlete']['lastname']}"
    else:
        organizer = "Club Organizer"

    try:
        distance, elevation_gain = get_event_route_distance_and_elevation(event['route_id'], access_token)
        distance_meters = int(distance)
        elevation_gain_meters = int(elevation_gain)
    except ValueError as e:
        print(e)

    # Prepare the event document for MongoDB
    event_document = {
        'source_type': 'strava',
        'source_group_id': int(club_id),
        'source_event_id': event_id,
        'source_group_name': club_name,
        'event_time_utc': event_time_utc,
        'meet_up_location': event['address'],
        'gps_coordinates': gps_coordinates,
        'distance_meters': distance_meters,
        'elevation_gain_meters': elevation_gain_meters,
        'organizer': organizer,
        'strava_url': f"https://www.strava.com/clubs/{club_id}/group_events/{event_id}",
        'title': event['title'],
        'description': event['description'],
        'route_map_url': event['route']['map_urls']['url'],
        'is_active': True,
        'raw_event': event
    }

    # DEBUG: print event_document without raw_event
    # print({k: v for k, v in event_document.items() if k != 'raw_event'})

    # Add the UpdateOne operation to the list
    operations.append(
        UpdateOne(
            {'source_type': 'strava', 'source_group_id': int(club_id), 'source_event_id': event_id},
            {'$set': event_document},
            upsert=True
        )
    )

# Backfill strava_routes that are active and after the start of the week
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
    except ValueError as e:
        print(e)
    
    # Prepare the event document for MongoDB
    update_event_document = {
        'distance_meters': distance_meters,
        'elevation_gain_meters': elevation_gain_meters,
        'route_map_url': strava_map_url,
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