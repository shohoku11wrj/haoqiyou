from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils.event_storage import (
    DEFAULT_EVENTS_FILE,
    load_events_for_runtime,
    save_events_to_storage,
)
import os
import pytz
import requests

# Load environment variables from .env file
load_dotenv()

# Local storage path
EVENTS_FILE_PATH = DEFAULT_EVENTS_FILE

# Google Maps API (unused but kept for compatibility)
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
access_token, _ = refresh_access_token(
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
)


def get_start_of_week():
    now = datetime.now(pytz.utc)
    start_of_week = now - timedelta(
        days=now.weekday(),
        hours=now.hour,
        minutes=now.minute,
        seconds=now.second,
        microseconds=now.microsecond,
    )
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
start_of_week_utc = get_start_of_week().astimezone(pytz.utc).replace(tzinfo=None)
all_events = load_events_for_runtime()
backfill_event_count = 0
updated = False

for event in all_events:
    if not event.get('is_active', True):
        continue
    event_time = event.get('event_time_utc')
    if not event_time or event_time < start_of_week_utc:
        continue
    if event.get('source_type') == 'strava':
        continue

    strava_url = event.get('strava_url')
    if not strava_url:
        continue

    if event.get('is_backfilled'):
        continue

    try:
        strava_route_id = int(strava_url.rstrip('/').split('/')[-1])
    except (ValueError, AttributeError) as exc:
        print(f"Skipping event {event.get('_id')} with invalid strava_url {strava_url}: {exc}")
        continue

    route_details = get_route_details(strava_route_id, access_token)
    distance = route_details.get('distance')
    elevation_gain = route_details.get('elevation_gain')
    strava_map_url = route_details.get('map_urls', {}).get('url')
    route_polyline = route_details.get('map', {}).get('summary_polyline', '')

    try:
        distance_meters = int(distance) if distance is not None else 0
    except (TypeError, ValueError):
        distance_meters = 0

    try:
        elevation_gain_meters = int(elevation_gain) if elevation_gain is not None else 0
    except (TypeError, ValueError):
        elevation_gain_meters = 0

    event.update({
        'distance_meters': distance_meters,
        'elevation_gain_meters': elevation_gain_meters,
        'route_map_url': strava_map_url,
        'route_polyline': route_polyline,
        'raw_event': route_details,
        'is_backfilled': True
    })

    backfill_event_count += 1
    updated = True

print(f"Backfilled {backfill_event_count} strava_routes")

if updated:
    save_events_to_storage(all_events, EVENTS_FILE_PATH)
    print(f"Saved updated events to {EVENTS_FILE_PATH}")
else:
    print("No updates written to storage")
