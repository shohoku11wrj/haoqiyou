
from dotenv import load_dotenv
from pymongo import MongoClient
import datetime
import os
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

# 本地时区
local_tz = pytz.timezone('America/Los_Angeles')  # Change this to your local time zone

# 获取当前时间所在周的周一00:00AM时间, 切不能小于当前时间
def get_start_of_week():
    now = datetime.datetime.now(pytz.utc)  # 使用UTC时间
    start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    if start_of_week <= now:
        start_of_week = start_of_week - datetime.timedelta(days=7)
    return start_of_week

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
        event_time_utc = datetime.datetime.strptime(event['event_time_utc'], '%Y-%m-%dT%H:%M:%S.%f+00:00')
        event_time_utc = event_time_utc.replace(tzinfo=None)  # Remove the timezone info
        event['event_time_utc'] = event_time_utc
    all_events_list.append(event)


# Split the events into two lists by start of today, one list for future events and one list for past events
start_of_today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
print(f"Start of today: {start_of_today}")
future_events_list = [event for event in all_events_list if event['event_time_utc'] > start_of_today]
future_events_list.sort(key=lambda x: x['event_time_utc'])
past_events_list = [event for event in all_events_list if event not in future_events_list]
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

# 生成HTML内容
html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strava Club Events</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #6d6d78;
        }
        .event {
            border: 1px solid #ccc;
            margin: 10px;
            padding: 10px;
            position: relative;
            margin-bottom: 20px;
            padding-left: 60px; /* Add padding to avoid overlap with date-box */
        }
        .event-section {
            display: flex;
            flex-direction: column;
            margin: 0 10px;
        }
        .event-title {
            font-size: 1.2em;
            font-weight: bold;
        }
        .event-details {
            display: flex;
            flex-direction: column;
        }
        .date-box {
            position: absolute;
            top: 0;
            left: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 10px;
        }
        .event-section:first-child {
            flex: 0 0 300px; /* Fixed width for the first column */
        }
        .event-section:nth-child(2) {
            flex: 0 0 350px; /* Fixed width for the second column */
            max-width: 350px; /* Restrict maximum width */
        }
        .event-section:nth-child(3) {
            display: flex;
            flex-direction: column; /* Ensure row by row layout */
        }
        .date-box {
            min-width: 60px;
            border: 1px solid #dfdfe8;
            display: inline-block;
            text-align: center;
        }
        .date-box .date {
            margin-top: 8px;
            color: #fc5200;
            font-size: 24px;
            line-height: 20px;
        }
        .meet-up {
            color: #6d6d78;
        }
        @media (min-width: 1440px) {
            .event {
                display: flex;
                flex-direction: row;
            }
            .event-section {
                flex-direction: column;
                margin-bottom: 0;
            }
            .event-details {
                flex-direction: row;
            }
            .date-box {
                flex-direction: row;
                align-items: flex-start;
            }
            .event-details div {
                margin-right: 10px;
                margin-bottom: 0;
            }
        }
    </style>
</head>
<body>
    <div id="events-container">
"""

def gen_div_for_events_from_list(events_list):
    events_div = ""
    for event in events_list:
        # 时间
        # Convert the event's event_time_utc from datetime.datetime to local time zone
        event_time_utc = event['event_time_utc'].replace(tzinfo=pytz.utc)
        event_time_local = event_time_utc.astimezone(local_tz)
        event_time_str = event_time_local.strftime('%H:%M %p')  # 12-hour format with AM/PM
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
        source_event_url = event['strava_url'] if event['source_type'] == 'strava' else ""
        if source_event_url == "" and 'source_url' in event:
            source_event_url = event['source_url']
        source_group_name = event['source_group_name']
        if event['source_type'] == 'strava':
            source_group_name = f"Strava Club - {event['source_group_name']}"
        elif event['source_type'] == 'wechat':
            source_group_name = f"微信群 - {event['source_group_name']}"
        elif event['source_type'] == 'news':
            source_group_name = f"新闻 - {event['source_group_name']}"


        # TODO: if year is not current year, add year to the date-box
        events_div += f"""
        <div class="event">
            <div class="event-section">
                <div class="event-details">
                    <div class="date-box">
                        <div class="date">{day_str}</div>
                        <div class="month">{month_str}</div>
        """
        if year != datetime.datetime.now().year:
            events_div += f"""
                        <div class="year">{year}</div>
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
                <a href="{source_event_url}" target="_blank">
                    <img src="{event['route_map_url']}" alt="Route Image" width="100%">
                </a>
            </div>
            <div class="event-section">
                <div class="event-title">{event['title']}</div>
                <div class="event-description">发起人: {event['organizer']} <br></div>
                <div class="event-description">活动来自: <a href="{source_event_url}" target="_blank">{source_group_name}</a></div>
                <br>
                <div class="event-description">{event['description']}</div>
            </div>
        </div>
        """
    return events_div

# Generate the HTML content for future and past events
html_content += f"""
        <h2>Upcoming Events</h2>
"""
html_content += gen_div_for_events_from_list(future_events_list)

html_content += f"""
        <h2>Past Events</h2>
"""
html_content += gen_div_for_events_from_list(past_events_list)

# Close the HTML content
html_content += """
    </div>
</body>
</html>
"""

# Save the HTML content to a file
with open('index.html', 'w', encoding='utf-8') as file:
    file.write(html_content)