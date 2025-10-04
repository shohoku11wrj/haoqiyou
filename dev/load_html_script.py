# dev/load_html_script.py

from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import sys
import pytz

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.event_storage import DEFAULT_EVENTS_FILE, load_events_for_runtime
from utils.load_html_utils import (
    get_start_of_week,
    gen_div_for_events_from_list,
    gen_gmp_advanced_marker_for_events_from_list,
    get_overlapping_gps_coords,
    insert_shift_to_event_markers,
    serialize_event_markers_to_string,
)

# Load environment variables from .env file
load_dotenv()

# 本地时区
local_tz = pytz.timezone('America/Los_Angeles')  # Change this to your local time zone

# Fetch events for the dev view (~90 days back)
start_of_week_utc = get_start_of_week()
start_of_week_naive = start_of_week_utc.astimezone(pytz.utc).replace(tzinfo=None)
two_months_before = start_of_week_naive - timedelta(days=90)
print(f"Start of the week (UTC): {start_of_week_naive}")

all_events = load_events_for_runtime(active_only=True)
all_events_list = [
    event for event in all_events
    if event.get('event_time_utc') and event['event_time_utc'] >= two_months_before
]

print(f"Loaded {len(all_events_list)} active events from {DEFAULT_EVENTS_FILE}")

# Split the events into three lists
six_hours_before = datetime.now(pytz.utc).replace(tzinfo=None) - timedelta(hours=6)
print(f"Six hours before: {six_hours_before}")
days_difference = datetime.now(pytz.utc).replace(tzinfo=None) + timedelta(days=14)
future_events_list = [
    event for event in all_events_list
    if six_hours_before <= event['event_time_utc'] <= days_difference
]
planning_events_list = [
    event for event in all_events_list
    if event['event_time_utc'] > days_difference
]
past_events_list = [
    event for event in all_events_list
    if event['event_time_utc'] < six_hours_before
]

# Sort the events
future_events_list.sort(key=lambda x: x['event_time_utc'])
planning_events_list.sort(key=lambda x: x['event_time_utc'])
past_events_list.sort(key=lambda x: x['event_time_utc'], reverse=True)

# DEBUG: 在CLI中打印events的数量
print(f"Total number of future events: {len(future_events_list)}")
print(f"Total number of planning events: {len(planning_events_list)}")
print(f"Total number of past events: {len(past_events_list)}")

##########################################################################################################
# 开始创建 html_content                                                                                   #
##########################################################################################################

events_list_content = """
    <h2><span style=\"opacity: 0;\">U</span>Pcoming Events <img src=\"https://maps.google.com/mapfiles/ms/icons/green-dot.png\" alt=\"Green Marker\" /></h2>
    <div class=\"events-container\">
"""

events_list_content += gen_div_for_events_from_list(future_events_list)

events_list_content += f"""
        </div>
        <h2>Planning Events <img src=\"https://maps.google.com/mapfiles/ms/icons/blue-dot.png\" alt=\"Blue Marker\" /></h2>
        <div class=\"events-container\">
"""
events_list_content += gen_div_for_events_from_list(planning_events_list)

events_list_content += f"""
        </div>
        <h2>Past Events <img src=\"https://maps.google.com/mapfiles/ms/icons/yellow-dot.png\" alt=\"Yellow Marker\" /></h2>
        <div class=\"events-container\">
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
with open('dev/dev_index_template.html', 'r', encoding='utf-8') as file:
    index_template = file.read()

# Sample output: Aug 1st (2024) 9:39 PM PDT
current_time_str_PDT = datetime.now(local_tz).strftime('%D %H:%M')
index_html = index_template.replace('{{current_time_str_PDT}}', current_time_str_PDT)
index_html = index_html.replace('{{list_content}}', events_list_content)
index_html = index_html.replace("'{{map_content}}'", map_content)

# Save the index_html to a file
with open('dev/index.html', 'w', encoding='utf-8') as file:
    file.write(index_html)
