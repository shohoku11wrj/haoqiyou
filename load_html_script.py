# load_html_utils.py

from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path
from utils.load_html_utils import (
    get_start_of_week,
    gen_div_for_events_from_list,
    gen_gmp_advanced_marker_for_events_from_list,
    get_overlapping_gps_coords,
    insert_shift_to_event_markers,
    serialize_event_markers_to_string
)
import json
import pytz

# Load environment variables from .env file
load_dotenv()

# Local storage paths
BASE_DIR = Path(__file__).resolve().parent
EVENTS_FILE_PATH = BASE_DIR / 'storage' / 'events.json'

# 本地时区
local_tz = pytz.timezone('America/Los_Angeles')  # Change this to your local time zone


def unwrap_number_long(value):
    if isinstance(value, dict) and '$numberLong' in value:
        try:
            return int(value['$numberLong'])
        except (ValueError, TypeError):
            return value['$numberLong']
    return value


def unwrap_date(value):
    if isinstance(value, dict) and '$date' in value:
        return value['$date']
    return value


def normalize_event_for_runtime(event):
    if not isinstance(event, dict):
        return event
    if 'source_group_id' in event:
        event['source_group_id'] = unwrap_number_long(event.get('source_group_id'))
    if 'source_event_id' in event:
        event['source_event_id'] = unwrap_number_long(event.get('source_event_id'))
    if 'event_time_utc' in event:
        event['event_time_utc'] = unwrap_date(event.get('event_time_utc'))
    return event

# Fetch events from local JSON storage and filter by start of the current week
start_of_week_utc = get_start_of_week()
start_of_week_naive = start_of_week_utc.astimezone(pytz.utc).replace(tzinfo=None)
print(f"Start of the week (UTC): {start_of_week_naive}")

events_data = []
if EVENTS_FILE_PATH.exists():
    try:
        with EVENTS_FILE_PATH.open('r', encoding='utf-8') as events_file:
            events_data = json.load(events_file)
            events_data = [normalize_event_for_runtime(event) for event in events_data]
    except json.JSONDecodeError as exc:
        print(f"Failed to load events from {EVENTS_FILE_PATH}: {exc}")

all_events_list = []
for event in events_data:
    if not event.get('is_active', True):
        continue

    event_time_str = event.get('event_time_utc')
    if not event_time_str:
        continue

    normalized_time_str = event_time_str.replace('Z', '+00:00')
    try:
        event_time_dt = datetime.fromisoformat(normalized_time_str)
    except ValueError:
        print(f"Skipping event {event.get('source_event_id')} due to invalid timestamp: {event_time_str}")
        continue

    if event_time_dt.tzinfo is None:
        event_time_dt = event_time_dt.replace(tzinfo=pytz.utc)

    event_time_utc = event_time_dt.astimezone(pytz.utc).replace(tzinfo=None)
    # load all events from the storage, instead of filtering by start_of_week_utc
    # if event_time_utc < start_of_week_naive:
    #    continue

    event['event_time_utc'] = event_time_utc
    event.setdefault('_id', f"{event.get('source_type', 'event')}-{event.get('source_group_id', 'unknown')}-{event.get('source_event_id', 'unknown')}")
    all_events_list.append(event)

print(f"Loaded {len(all_events_list)} events from {EVENTS_FILE_PATH}")

# Sort events by date
all_events_list.sort(key=lambda x: x['event_time_utc'])

# Split the events into two lists by 6 hours before the current time;
# one list for future events (ongoing events started in 6 hours, future events),
# and one list for past events.
six_hours_before = datetime.now(pytz.utc).replace(tzinfo=None) - timedelta(hours=6)
print(f"Six hours before: {six_hours_before}")
days_difference = datetime.now(pytz.utc).replace(tzinfo=None) + timedelta(days=14)
future_events_list = [event for event in all_events_list if event['event_time_utc'] >= six_hours_before and event['event_time_utc'] <= days_difference]
planning_events_list = [event for event in all_events_list if event['event_time_utc'] > days_difference]
past_events_list = [event for event in all_events_list if event['event_time_utc'] < six_hours_before]

# Sort the events
future_events_list.sort(key=lambda x: x['event_time_utc'])
planning_events_list.sort(key=lambda x: x['event_time_utc'])
past_events_list.sort(key=lambda x: x['event_time_utc'], reverse=True)  # most recent first

# DEBUG: Print number of events
print(f"Total number of future events: {len(future_events_list)}")
print(f"Total number of planning events: {len(planning_events_list)}")
print(f"Total number of past events: {len(past_events_list)}")

# DEBUG: Uncomment to print all club events data
# for event in future_events_list:
#     club_id = event.get('source_group_id', 'N/A')
#     club_name = event.get('source_group_name', 'N/A')
#     print(f"Events for Club ID {club_id} & Club Name \"{club_name}\":")
#     if event.get('source_event_id') == 1726014:
#         print(event.get('raw_event', 'No raw event data'))
#     else:
#         print(f"  Event Id: {event.get('source_event_id', 'N/A')}")
#         print(f"  Event Name: {event.get('title', 'No title')}")
#         print(f"  Start Time: {event.get('event_time_utc', 'N/A')}")
#         print(f"  Start Address: {event.get('meet_up_location', 'N/A')}")
#         print(f"  Start Position GPS: {event.get('gps_coordinates', 'N/A')}")
#         print(f"  Route Image: {event.get('route_map_url', 'N/A')}")
#         print(f"  Organizer: {event.get('organizer', 'N/A')}")
#         print(f"  Club Name: {event.get('source_group_name', 'N/A')}")
#         print(f"  Description: {event.get('description', 'No description')}")
#         print("-" * 40)
#     print("~" * 40)

# DEBUG: 打印所有俱乐部的事件数据
# for event in future_events_list:
#     club_id = event['source_group_id']
#     club_name = event['source_group_name']
#     print(f"Events for Club ID {club_id} & Club Name \"{club_name}\":")
#     if event['source_event_id'] == 1726014:
#         print(event['raw_event'])
#     else:
#         print(f"  Event Id: {event['source_event_id']}")
#         print(f"  Event Name: {event['title']}")
#         print(f"  Start Time: {event['event_time_utc']}")
#         print(f"  Start Address: {event['meet_up_location']}")
#         print(f"  Start Position GPS: {event['gps_coordinates']}")
#         print(f"  Route Image: {event['route_map_url']}")
#         print(f"  Organizer: {event['organizer']}")
#         print(f"  Club Name: {event['source_group_name']}")
#         print(f"  Description: {event['description']}")
#         print("-" * 40)
#     print("~" * 40)


##########################################################################################################
# 开始创建 html_content                                                                                   #
##########################################################################################################

events_list_content = """
    <h2><span style="opacity: 100;">U</span>Pcoming Events <img src="http://maps.google.com/mapfiles/ms/icons/green-dot.png" alt="Green Marker" /></h2>
    <div class="events-container">
"""

events_list_content += gen_div_for_events_from_list(future_events_list)


events_list_content += f"""
        </div>
        <h2>Planning Events <img src="http://maps.google.com/mapfiles/ms/icons/blue-dot.png" alt="Blue Marker" /></h2>
        <div class="events-container">
"""
events_list_content += gen_div_for_events_from_list(planning_events_list)


events_list_content += f"""
        </div>
        <h2>Past Events <img src="http://maps.google.com/mapfiles/ms/icons/yellow-dot.png" alt="Yellow Marker" /></h2>
        <div class="events-container">
"""
events_list_content += gen_div_for_events_from_list(past_events_list)

# Close the last events-container div
events_list_content += """
    </div>
"""

event_markers = []
event_markers.extend(gen_gmp_advanced_marker_for_events_from_list(past_events_list, 'past'))
event_markers.extend(gen_gmp_advanced_marker_for_events_from_list(future_events_list, 'upcoming'))
event_markers.extend(gen_gmp_advanced_marker_for_events_from_list(planning_events_list, 'planning'))

overlapping_gps_coords = get_overlapping_gps_coords(all_events_list)
insert_shift_to_event_markers(event_markers, overlapping_gps_coords)

map_content = serialize_event_markers_to_string(event_markers)

# Read the index_template file
with open('index_template.html', 'r', encoding='utf-8') as file:
    index_template = file.read()

# Sample output: Aug 1st (2024) 9:39 PM PDT
current_time_str_PDT = datetime.now(local_tz).strftime('%D %H:%M')
index_html = index_template.replace('{{current_time_str_PDT}}', current_time_str_PDT)
index_html = index_html.replace('{{list_content}}', events_list_content)
index_html = index_html.replace("'{{map_content}}'", map_content)

# Add the events data as a JavaScript variable
script_tag = f"""
<script>
    // Pass the events data to the frontend
    const events = {0};
</script>
""".format(map_content)

# Insert the script tag before the closing body tag
index_html = index_html.replace('</body>', f"{script_tag}\n</body>")

# Save the index_html to a file
with open('index.html', 'w', encoding='utf-8') as file:
    file.write(index_html)
