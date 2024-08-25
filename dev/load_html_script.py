from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import os
import re
import requests
import pytz

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
# 生成 HTML body content                                                                                 #
##########################################################################################################

def gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, source_group_name):
    # Convert URLs in the description to hyperlinks
    event_description = convert_urls_to_links(event['description'])
    popup_div = f"""
        <div id="event-{event['_id']}" style="display: none;">
            <div class="event-title-row">
                <div class="date-box">
                    <div class="date">{day_str}</div>
                    <div class="month">{month_str}</div>
    """
    if year != datetime.now().year:
        popup_div += f"""
                    <div class="year">{year}</div>
        """

    popup_div += f"""
                </div>
                <div class="event-title">{event['title']}</div>
            </div>
            <p class="event-description">{event_description}</p>
            <a href="{source_event_url}" target="_blank" class="event-link">
                <img src="{event['route_map_url']}" alt="Route Image" width="100%">
            </a>
            <p><strong>时间:</strong> {event_time_str}, {day_of_week}, {month_str} {day_str}, {year}</p>
            <p><strong>集合GPS:</strong> {gps_coordinates_str}</p>
            <p><strong>集合地点:</strong> {event['meet_up_location']}</p>
        """
    if 'distance_meters' in event and event['distance_meters'] > 0:
        popup_div += f"""
            <p><strong>总路程::</strong> {distance_str}</p>
            <p><strong>总爬坡:</strong> {elevation_gain_str}</p>
        """
    popup_div += f"""
        <p><strong>发起人:</strong> {event['organizer']}</p>
        <p><strong>活动来源:</strong> <a href="{source_event_url}" target="_blank">{source_group_name}</a></p>
    """
    if 'expected_participants_number' in event and event['expected_participants_number'] != "" and event['expected_participants_number'] != "0":
        popup_div += f"""
            <p><strong>预计人数:</strong> {event['expected_participants_number']}</p>
        """

    if 'actual_participants_number' in event and event['actual_participants_number'] != "" and event['actual_participants_number'] != "0":
        popup_div += f"""
            <p><strong>实际人数:</strong> {event['actual_participants_number']}</p>
        """

    # # Generate QR code for the event with URL: https://haoqiyou.net/?id=event-{event['_id']}
    # qr_code_url = f"https://haoqiyou.net/?id=event-{event['_id']}"
    # popup_div += f"""
    #     <p><strong>扫码查看活动:</strong></p>
    #     <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={qr_code_url}" alt="QR Code" width="150">
    # """

    popup_div += "</div>"
    return popup_div

def gen_div_for_events_from_list(events_list):
    events_div = ""
    for event in events_list:
        # 时间
        # Convert the event's event_time_utc from datetime.datetime to local time zone
        event_time_utc = event['event_time_utc'].replace(tzinfo=pytz.utc)
        event_time_local = event_time_utc.astimezone(local_tz)
        # 12-hour format with AM/PM
        event_time_str = event_time_local.strftime('%I:%M %p').lstrip('0')
        # Extract month and day separately for the date-box
        year = event_time_utc.year
        month_str = event_time_local.strftime('%b').upper()
        day_str = event_time_local.strftime('%d')
        day_of_week = event_time_local.strftime('%A')  # Full weekday name
        # 地点
        # Format the GPS coordinates to at most 5 digits after floats, and without brackets
        gps_coordinates_str = event['gps_coordinates']

        try:
            distance = event['distance_meters']
            elevation_gain = event['elevation_gain_meters']
            distance_km = distance / 1000
            distance_miles = distance_km * 0.621371
            elevation_gain_feet = elevation_gain * 3.28084
            distance_str = f"{distance_km:.2f} km ({distance_miles:.2f} miles)"
            elevation_gain_str = f"{int(elevation_gain):,} m ({int(elevation_gain_feet):,} ft)"
        except ValueError as e:
            print(e)
        
        # Source URL
        source_event_url = event.get('strava_url', "")
        if source_event_url == "" and 'source_url' in event:
            source_event_url = event['source_url']
        source_group_name = event['source_group_name']
        if event['source_type'] == 'strava':
            source_group_name = f"Strava Club - {event['source_group_name']}"
        elif event['source_type'] == 'wechat':
            source_group_name = f"微信群 - {event['source_group_name']}"
        elif event['source_type'] == 'news':
            source_group_name = f"新闻 - {event['source_group_name']}"

        # Add the extra-event class if the event belongs to extra_event_group_ids
        event_class = "extra-event" if event['source_group_id'] in extra_event_group_ids else "selected-event"
        event_id = event['_id']
        event_url = f"?id=event-{event_id}"

        # If year is not current year, add year to the date-box
        events_div += f"""
        <div class="event {event_class}" data-event-id="event-{event_id}">
            <a href="{event_url}" class="event-link"></a>
            <div class="event-section">
        """
        events_div += gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, source_group_name)
        events_div += f"""
                <div class="event-details">
                    <div class="date-box">
                        <div class="date">{day_str}</div>
                        <div class="month">{month_str}</div>
        """
        if year != datetime.now().year:
            events_div += f"""
                        <div class="year">{year}</div>
            """
        events_div += f"""
                        <div class="date-relative" event-date="{event_time_local}"></div>
        """
        events_div += f"""
                    </div>
                    <div>
                        <strong>{event_time_str}</strong> {day_of_week}<br>
                        <span class="meet-up">集合GPS:</span> {gps_coordinates_str}
                    </div>
                </div>
                <div>
                    <span class="meet-up">集合地点:</span> {event['meet_up_location']} <br>
        """
        if 'distance_meters' in event and event['distance_meters'] > 0:
            events_div += f"""
                    <span class="meet-up">总路程:</span> {distance_str} <br>
                    <span class="meet-up">总爬坡:</span> {elevation_gain_str} <br>
            """

        if 'expected_participants_number' in event and event['expected_participants_number'] != "" and event['expected_participants_number'] != "0":
            events_div += f"""
                    <span class="meet-up">预计人数:</span> {event['expected_participants_number']} <br>
            """

        if 'actual_participants_number' in event and event['actual_participants_number'] != "" and event['actual_participants_number'] != "0":
            events_div += f"""
                    <span class="meet-up">实际人数:</span> {event['actual_participants_number']} <br>
            """
        
        events_div += f"""
                </div>
            </div>
            <div class="event-section">
                <a href="{source_event_url}" target="_blank" class="event-link">
                    <img src="{event['route_map_url']}" alt="Route Image" width="100%">
                </a>
            </div>
            <div class="event-section">
                <div class="event-title">{event['title']}</div> <br>
                <div class="event-description">发起人: {event['organizer']}</div> <br>
                <div class="event-description">活动来源: <a href="{source_event_url}" target="_blank" class="event-link">{source_group_name}</a></div>
            </div>
        </div>
        """
    return events_div

def gen_gmp_advanced_marker_for_events_from_list(event_list):
    events_marker=""
    for event in event_list:
        event_type = "extra-event" if event['source_group_id'] in extra_event_group_ids else "selected-event"
        event_title=event['title']
        event_id=f"event-{event['_id']}"
        gps_coordinates_str = event['gps_coordinates']
        if gps_coordinates_str=="":
            continue
        gps_coordinates_str='{ lat: ' + gps_coordinates_str.replace(',',', lng: ') + ' }'
        events_marker += f"""
            {'{'}
                title: "{event_title}",
                position: {gps_coordinates_str},
                id: "{event_id}",
            {'}'},
        """
    return events_marker

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

map_content = gen_gmp_advanced_marker_for_events_from_list(past_events_list)
map_content += gen_gmp_advanced_marker_for_events_from_list(future_events_list)
map_content += gen_gmp_advanced_marker_for_events_from_list(planning_events_list)

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