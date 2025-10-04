# NorCal2024/load_html_script.py

from datetime import datetime
from dotenv import load_dotenv
import os
import sys
import pytz

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.event_storage import DEFAULT_EVENTS_FILE, load_events_for_runtime
from utils.load_html_utils import (
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

# NorCal specific filters
NORCAL_GROUP_IDS = {59884023036, 1157973}
INCLUDE_SOURCE_TYPES = {'wechat'}
INCLUDE_EVENT_IDS = {'675cbf464d14b254128dbbf1'}

all_events = load_events_for_runtime(active_only=True)
all_events_list = []
for event in all_events:
    if event.get('_id') in INCLUDE_EVENT_IDS:
        all_events_list.append(event)
        continue
    if event.get('source_type') in INCLUDE_SOURCE_TYPES:
        all_events_list.append(event)
        continue
    if event.get('source_group_id') in NORCAL_GROUP_IDS:
        all_events_list.append(event)
        continue

all_events_list.sort(key=lambda x: x['event_time_utc'], reverse=True)

print(f"Loaded {len(all_events_list)} NorCal events from {DEFAULT_EVENTS_FILE}")

##########################################################################################################
# 开始创建 html_content                                                                                   #
##########################################################################################################

events_list_content = """
    <h2><span style=\"opacity: 0;\">U</span>北加州骑行团2024骑行记录回顾 <img src=\"https://maps.google.com/mapfiles/ms/icons/green-dot.png\" alt=\"Green Marker\" /></h2>
    <div class=\"events-container\">
"""

events_list_content += gen_div_for_events_from_list(all_events_list)

# Close the last events-container div
events_list_content += """
    </div>
"""


event_markers = []
event_markers.extend(gen_gmp_advanced_marker_for_events_from_list(all_events_list, 'upcoming'))

overlapping_gps_coords = get_overlapping_gps_coords(all_events_list)
insert_shift_to_event_markers(event_markers, overlapping_gps_coords)

map_content = serialize_event_markers_to_string(event_markers)


# Read the index_template file
with open('NorCal2024/index_template.html', 'r', encoding='utf-8') as file:
    index_template = file.read()

# Sample output: Aug 1st (2024) 9:39 PM PDT
current_time_str_PDT = datetime.now(local_tz).strftime('%D %H:%M')
index_html = index_template.replace('{{current_time_str_PDT}}', current_time_str_PDT)
index_html = index_html.replace('{{list_content}}', events_list_content)
index_html = index_html.replace("'{{map_content}}'", map_content)

# Save the index_html to a file
with open('NorCal2024/index.html', 'w', encoding='utf-8') as file:
    file.write(index_html)
