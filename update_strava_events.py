from __future__ import annotations

from dotenv import load_dotenv
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytz
import requests

from utils import extract_route_from_ridewithgps

# Load environment variables from .env file
load_dotenv()

# Local storage paths
BASE_DIR = Path(__file__).resolve().parent
EVENTS_FILE_PATH = BASE_DIR / 'storage' / 'events.json'

# Google Maps API
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

# Strava API AccessToken
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
STRAVA_REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')
access_token = None


def wrap_number_long(value: Any) -> Dict[str, str] | None:
    """Wrap numeric identifiers using Mongo Extended JSON style."""
    if value is None:
        return None
    if isinstance(value, dict) and "$numberLong" in value:
        return value
    return {"$numberLong": str(value)}


def isoformat_datetime(value: datetime.datetime) -> str:
    """Return an ISO-8601 string including milliseconds when absent."""
    iso_value = value.isoformat()
    if value.microsecond == 0 and "." not in iso_value:
        if iso_value.endswith("Z"):
            return f"{iso_value[:-1]}.000Z"
        for tz_sep in ("+", "-"):
            idx = iso_value.rfind(tz_sep)
            if idx > 10:
                base = iso_value[:idx]
                suffix = iso_value[idx + 1:]
                return f"{base}.000{tz_sep}{suffix}"
        return f"{iso_value}.000"
    return iso_value


def wrap_date(value: Any) -> Dict[str, str] | None:
    """Encapsulate datetime strings using Mongo Extended JSON $date."""
    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        return value
    if isinstance(value, datetime.datetime):
        iso_value = isoformat_datetime(value)
    else:
        iso_value = str(value)
    return {"$date": iso_value}


def ensure_list_of_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False



def clean_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested = clean_dict(value)
            if nested:
                cleaned[key] = nested
            continue
        if isinstance(value, list):
            cleaned_list = [item for item in value if item not in (None, "")]
            cleaned[key] = cleaned_list
            continue
        cleaned[key] = value
    return cleaned


def dehydrate_event_document(event_document: Dict[str, Any]) -> Dict[str, Any]:
    dehydrated = {k: v for k, v in event_document.items() if k != 'raw_event'}

    dehydrated['source_event_id'] = wrap_number_long(dehydrated.get('source_event_id'))
    dehydrated['source_group_id'] = wrap_number_long(dehydrated.get('source_group_id'))
    dehydrated['event_time_utc'] = wrap_date(dehydrated.get('event_time_utc'))

    if 'event_picture_urls' in dehydrated:
        dehydrated['event_picture_urls'] = ensure_list_of_strings(dehydrated['event_picture_urls'])
    elif 'event_picture_url' in dehydrated:
        dehydrated['event_picture_urls'] = ensure_list_of_strings(dehydrated['event_picture_url'])
        dehydrated.pop('event_picture_url', None)
    else:
        dehydrated['event_picture_urls'] = []

    if not dehydrated.get('source_url'):
        dehydrated['source_url'] = dehydrated.get('strava_url', '')

    return clean_dict(dehydrated)


def _load_existing_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open('r', encoding='utf-8') as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: unable to read existing events from {path}: {exc}")
    return []


def _strava_event_key(event: Dict[str, Any]) -> Optional[str]:
    if event.get('source_type') != 'strava':
        return None

    source_event_id = event.get('source_event_id')
    if isinstance(source_event_id, dict):
        source_event_id = source_event_id.get('$numberLong') or source_event_id.get('$oid')
    if source_event_id:
        return f"id:{source_event_id}"

    strava_url = (event.get('strava_url') or event.get('source_url') or '').strip()
    if strava_url:
        return f"url:{strava_url}"

    if event.get('_id'):
        return f"_id:{event['_id']}"

    return None


def _event_time_sort_key(event: Dict[str, Any]) -> datetime.datetime:
    raw_time: Any = event.get('event_time_utc')
    if isinstance(raw_time, dict):
        raw_time = raw_time.get('$date')
    if isinstance(raw_time, str):
        iso_value = raw_time.replace('Z', '+00:00')
        try:
            dt = datetime.datetime.fromisoformat(iso_value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.datetime(9999, 12, 31, tzinfo=datetime.timezone.utc)


def _merge_event_fields(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)

    for key, new_value in incoming.items():
        if key == 'raw_event':
            merged[key] = new_value
            continue

        current_value = existing.get(key)
        if _is_empty_value(new_value) and not _is_empty_value(current_value):
            continue
        merged[key] = new_value

    return merged


def _merge_events(existing_events: List[Dict[str, Any]], new_strava_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    strava_events: Dict[str, Dict[str, Any]] = {}

    for event in existing_events:
        key = _strava_event_key(event)
        if key:
            strava_events[key] = event
        else:
            merged.append(event)

    for event in new_strava_events:
        key = _strava_event_key(event)
        if key:
            if key in strava_events:
                strava_events[key] = _merge_event_fields(strava_events[key], event)
            else:
                strava_events[key] = event
        else:
            merged.append(event)

    merged.extend(strava_events.values())
    merged.sort(key=_event_time_sort_key)
    return merged

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
    '908336',    # Ruekn Bicci Gruppo (Southern California)
]

# Google Maps APIs

def get_gps_by_address(address):
    print(address)
    try:
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": GOOGLE_MAPS_API_KEY
        }
        
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                location = data['results'][0]['geometry']['location']
                lat = location['lat']
                lng = location['lng']
                gps_coordinates = f"{lat:.5f}, {lng:.5f}"
                return gps_coordinates
        return ''
    except Exception as e:
        print(f"Error fetching GPS coordinates for address: {address}")
        print(f"Error details: {str(e)}")
        return ''

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
        print(f"Error: {response.status_code}, url: {url}")
        return None

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
        print(f"Error: {response.status_code}, url: {url}")
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
print(f"Total number of deduped Strava events: {len(all_events_list)}")

# Sort the events by their start time
all_events_list.sort(key=lambda x: datetime.datetime.strptime(x[2]['upcoming_occurrences'][0], '%Y-%m-%dT%H:%M:%SZ'))

event_documents: List[Dict[str, Any]] = []

for club_id, event_id, event in all_events_list:
    club_name = event['club']['name']
    print(f"Processing event {event_id} for club {club_id}:{club_name}")
    event_time_utc = datetime.datetime.strptime(event['upcoming_occurrences'][0], '%Y-%m-%dT%H:%M:%SZ')
    event_time_utc = event_time_utc.replace(tzinfo=pytz.utc)
    event_time_utc_iso = event_time_utc.isoformat()
    # Format the GPS coordinates to at most 5 digits after floats, and without brackets
    gps_coordinates = ', '.join(map(str, [round(coord, 5) for coord in event['start_latlng']])) if event['start_latlng'] else ''
    if gps_coordinates == '' and event['address'] != '':
        # Fetch GPS coordinates from address using Google Maps API
        gps_coordinates = get_gps_by_address(event['address'])
        print(gps_coordinates)
    # Check if organizing_athlete is not None
    if event['organizing_athlete'] is not None:
        organizer = f"{event['organizing_athlete']['firstname']} {event['organizing_athlete']['lastname']}"
    else:
        organizer = "Club Organizer"

    try:
        distance, elevation_gain = get_event_route_distance_and_elevation(event['route_id'], access_token)
        if distance is None or elevation_gain is None:
            distance = 0
            elevation_gain = 0
        distance_meters = int(distance)
        elevation_gain_meters = int(elevation_gain)
        if event['route'] is not None:
            route_polyline = event['route']['map']['summary_polyline']
        else:
            route_polyline = ''
    except ValueError as e:
        print(e)

    # Prepare the event document for JSON storage
    event_document = {
        '_id': f"strava-{club_id}-{event_id}",
        'source_type': 'strava',
        'source_group_id': int(club_id),
        'source_event_id': event_id,
        'source_group_name': club_name,
        'event_time_utc': event_time_utc_iso,
        'meet_up_location': event['address'],
        'gps_coordinates': gps_coordinates,
        'distance_meters': distance_meters,
        'elevation_gain_meters': elevation_gain_meters,
        'organizer': organizer,
        'strava_url': f"https://www.strava.com/clubs/{club_id}/group_events/{event_id}",
        'title': event['title'],
        'description': event['description'],
        'route_map_url': event['route']['map_urls']['url'] if event['route'] is not None else '',
        'route_polyline': route_polyline,
        'is_active': True,
        'raw_event': event
    }

    # DEBUG: print event_document without raw_event
    # print({k: v for k, v in event_document.items() if k != 'raw_event'})
    event_documents.append(dehydrate_event_document(event_document))

existing_events = _load_existing_events(EVENTS_FILE_PATH)
merged_events = _merge_events(existing_events, event_documents)

EVENTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
with EVENTS_FILE_PATH.open('w', encoding='utf-8') as events_file:
    json.dump(merged_events, events_file, indent=2)

print(
    f"Stored {len(event_documents)} Strava events (total records: {len(merged_events)}) in {EVENTS_FILE_PATH}"
)
