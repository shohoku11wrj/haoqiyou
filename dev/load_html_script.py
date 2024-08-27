# dev/load_html_script.py

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import os
import re
import sys
import pytz

# Add the root directory to sys.pathfrom
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.load_html_utils import gen_div_for_events_from_list, gen_gmp_advanced_marker_for_events_from_list

# Load environment variables from .env file
load_dotenv()

# MongoDB connection setup
MONGO_CONNECTION_STRING = os.getenv('MONGO_CONNECTION_STRING')
RIDE_EVENT_DB_NAME = os.getenv('RIDE_EVENT_DB_NAME')
RIDE_EVENTS_COLLECTION_NAME = os.getenv('RIDE_EVENTS_CITY_COLLECTION_NAME')
client = MongoClient(MONGO_CONNECTION_STRING)
db = client[RIDE_EVENT_DB_NAME]
collection = db[RIDE_EVENTS_COLLECTION_NAME]


# List of group_ids of extra events
extra_event_group_ids = [
    265,    # Los Gatos Bicycle Racing Club
    908336  # Ruekn Bicci Gruppo (Southern California)
]

# 本地时区
local_tz = pytz.timezone('America/Los_Angeles')  # Change this to your local time zone

# 获取当前时间所在周的周一00:00AM时间, 切不能小于当前时间
def get_start_of_week():
    now = datetime.now(pytz.utc)  # 使用UTC时间
    start_of_week = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    if start_of_week <= now:
        start_of_week = start_of_week - timedelta(days=7)
    return start_of_week

# 转移url成hyperlink成<a href="url" target="_blank">text</a>
def convert_urls_to_links(text):
    # case_1: 原文已经提供了<a>标签
    if re.search(r'<a href="([^"]+)" target="_blank">[^<]+</a>', text):
        return text
    # case_2: 原文提供了markdown形式[text](url)
    markdown_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    text = markdown_pattern.sub(r'<a href="\2" target="_blank">\1</a>', text)
    # case_3: 原文只有url
    url_pattern = re.compile(r'(?<!href=")(https?://[^\s]+)')
    text = url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)
    return text

# Fetch events from MongoDB where the start time is after the Monday of the current week
start_of_week_utc = get_start_of_week()
print(f"Start of the week (UTC): {start_of_week_utc}")
events_cursor = collection.find({
    'is_active': {'$eq': True},
    '$or': [
        {'event_time_utc': {'$gte': start_of_week_utc}},
        {'event_time_utc': {'$type': 'string', '$gte': start_of_week_utc.isoformat()}}
    ]
})

# Save all the fetched events in a list
all_events_list = []
for event in events_cursor:
    # Convert the event's event_time_utc to datetime.datetime object if it's a string, hint: string format 2024-07-26T15:30:00.000+00:00
    if isinstance(event['event_time_utc'], str):
        datetime_str = event['event_time_utc']
        dt, tz = datetime_str[:-6], datetime_str[-6:]
        event_time_tz = datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S.%f')
        # Parse the timezone part
        tz_hours, tz_minutes = int(tz[1:3]), int(tz[4:6])
        tz_delta = timedelta(hours=tz_hours, minutes=tz_minutes)
        if tz[0] == '-':
            tz_delta = -tz_delta
        # Apply the timezone to the datetime object
        event_time_tz = event_time_tz.replace(tzinfo=timezone(tz_delta))
        # convert to UTC
        event_time_utc = event_time_tz.astimezone(pytz.utc)
        event_time_utc = event_time_utc.replace(tzinfo=None)  # Ensure no timezone info
        event['event_time_utc'] = event_time_utc
    elif isinstance(event['event_time_utc'], datetime):
        event['event_time_utc'] = event['event_time_utc'].replace(tzinfo=None)  # Ensure no timezone info
    all_events_list.append(event)


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
past_events_list.sort(key=lambda x: x['event_time_utc'], reverse=True)  # you are so smart copilot #

# DEBUG: 在CLI中打印events的数量
print(f"Total number of future events: {len(future_events_list)}")
print(f"Total number of past events: {len(past_events_list)}")

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
    <h2><span style="opacity: 0;">U</span>Pcoming Events</h2>
    <div class="events-container">
"""

events_list_content += gen_div_for_events_from_list(future_events_list)


events_list_content += f"""
        </div>
        <h2>Planning Events</h2>
        <div class="events-container">
"""
events_list_content += gen_div_for_events_from_list(planning_events_list)


events_list_content += f"""
        </div>
        <h2>Past Events</h2>
        <div class="events-container">
"""
events_list_content += gen_div_for_events_from_list(past_events_list)

# Close the last events-container div
events_list_content += """
    </div>
"""

map_content = gen_gmp_advanced_marker_for_events_from_list(past_events_list, 'past')
map_content += gen_gmp_advanced_marker_for_events_from_list(future_events_list, 'upcoming')
map_content += gen_gmp_advanced_marker_for_events_from_list(planning_events_list, 'planning')

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