from datetime import datetime, timedelta
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
    265,  # Los Gatos Bicycle Racing Club
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
        event_time_utc = datetime.strptime(event['event_time_utc'], '%Y-%m-%dT%H:%M:%S.%f+00:00')
        event_time_utc = event_time_utc.replace(tzinfo=None)  # Remove the timezone info
        event['event_time_utc'] = event_time_utc
    elif isinstance(event['event_time_utc'], datetime):
        event['event_time_utc'] = event['event_time_utc'].replace(tzinfo=None)  # Ensure no timezone info
    all_events_list.append(event)


# Split the events into two lists by 6 hours before the current time;
# one list for future events (ongoing events started in 6 hours, future events),
# and one list for past events.
six_hours_before = datetime.now(pytz.utc).replace(tzinfo=None) - timedelta(hours=6)
print(f"Six hours before: {six_hours_before}")
one_month_later = datetime.now(pytz.utc).replace(tzinfo=None) + timedelta(days=30)
future_events_list = [event for event in all_events_list if event['event_time_utc'] >= six_hours_before and event['event_time_utc'] <= one_month_later]
planning_events_list = [event for event in all_events_list if event['event_time_utc'] > one_month_later]
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

# Sample output: Aug 1st (2024) 9:39 PM PDT
current_time_str_PDT = datetime.now(local_tz).strftime('%D %H:%M')

# 生成HTML内容
html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="haoqiyou.ico" type="image/x-icon">
    <link rel="shortcut icon" href="haoqiyou.ico" type="image/x-icon">
    <title>好骑友网(骑行活动收集器)</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            color: #6d6d78;
        }
        .top-bar {
            background-color: #c60c30; /* Deep red color */
            color: #fff; /* White font color */
            padding: 10px;
            text-align: center;
            border-bottom: 4px solid #fff; /* White border at the bottom */
        }
        /* Include the CSS here */
        #events-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); /* Adjust minmax value as needed */
            gap: 10px; /* Space between grid items */
            margin: 0 10px;
        }
        .event {
            border: 1px solid #ccc;
            padding: 10px;
            position: relative;
            padding-left: 60px; /* Add padding to avoid overlap with date-box */
            box-sizing: border-box; /* Include padding and border in element's total width and height */
        }
        .event-section {
            display: flex;
            flex-wrap: wrap; /* Allow wrapping of events */
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
        .event-description {
            white-space: pre-wrap; /* CSS3 */
            white-space: -moz-pre-wrap; /* Mozilla */
            white-space: -pre-wrap; /* Opera 4-6 */
            white-space: -o-pre-wrap; /* Opera 7 */
            word-wrap: break-word; /* Internet Explorer 5.5+ */
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
        .popup {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 80%;
            max-width: 600px;
            background-color: white;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
            padding: 20px;
            z-index: 1000;
            max-height: 100vh; /* Set maximum height to the viewport height */
            overflow-y: auto;
        }
        .popup-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 999;
        }
        .close-btn {
            float: right;
            cursor: pointer;
        }
    </style>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=UA-51069014-1"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        gtag('js', new Date());

        gtag('config', 'UA-51069014-1');
    </script>
</head>
<body>
"""

def gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, source_group_name):
    # Convert URLs in the description to hyperlinks
    event_description = convert_urls_to_links(event['description'])
    popup_div = f"""
            <div id="event-{event['_id']}" style="display: none;">
                <h2>{event['title']}</h2>
                <p class="event-description">{event_description}</p>
                <a href="{source_event_url}" target="_blank" class="event-link">
                    <img src="{event['route_map_url']}" alt="Route Image" width="100%">
                </a>
                <p><strong>时间:</strong> {event_time_str}, {day_of_week}, {month_str} {day_str}, {year}</p>
                <p><strong>集合GPS:</strong> {gps_coordinates_str}</p>
                <p><strong>集合地点:</strong> {event['meet_up_location']}</p>
                <p><strong>总路程::</strong> {distance_str}</p>
                <p><strong>总爬坡:</strong> {elevation_gain_str}</p>
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
        event_class = "extra-event" if event['source_group_id'] in extra_event_group_ids else ""

        # If year is not current year, add year to the date-box
        events_div += f"""
        <div class="event {event_class}" data-event-id="event-{event['_id']}">
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
                <div class="event-title">{event['title']}</div>
                <div class="event-description">发起人: {event['organizer']} <br></div>
                <div class="event-description">活动来源: <a href="{source_event_url}" target="_blank" class="event-link">{source_group_name}</a></div>
            </div>
        </div>
        """
    return events_div

# Generate the HTML content for future and past events
html_content += f"""
        <h2><span class="top-bar">好 骑 友</span>Upcoming Events</h2>
        <span>Updated on {current_time_str_PDT}</span>
"""

# Add a checkbox to switch displaying or hiding extra events
html_content += """
    <label>
        <input type="checkbox" id="toggleExtra">
        <span style="color:#0000ff">只显示精选活动</span>
    </label>
    <script>
        document.getElementById('toggleExtra').addEventListener('change', function() {
            var extraEvents = document.querySelectorAll('.extra-event');
            extraEvents.forEach(function(event) {
                event.style.display = this.checked ? 'none' : 'block';
                event.style.backgroundColor = this.checked ? 'transparent' : '#cad6e6' ;
            }, this);
        });
    </script>
    <div id="events-container">
"""

html_content += gen_div_for_events_from_list(future_events_list)


html_content += f"""
        </div>
        <h2>Planning Events</h2>
        <div id="events-container">
"""
html_content += gen_div_for_events_from_list(planning_events_list)


html_content += f"""
        </div>
        <h2>Past Events</h2>
        <div id="events-container">
"""
html_content += gen_div_for_events_from_list(past_events_list)

# Close the HTML content
html_content += """
    </div>
    <div class="popup-overlay" id="popup-overlay"></div>
    <div class="popup" id="popup">
        <span class="close-btn" id="close-btn">&times;</span>
        <div id="popup-content"></div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('.expand').forEach(function(link) {
                link.addEventListener('click', function(event) {
                    event.preventDefault();
                    const fullDescription = this.getAttribute('data-full-description');
                    this.parentElement.innerHTML = fullDescription;
                });
            });

            document.querySelectorAll('.event').forEach(function(eventDiv) {
                eventDiv.addEventListener('click', function(event) {
                    event.preventDefault();
                    const eventId = this.getAttribute('data-event-id');
                    const eventDetails = document.getElementById(eventId).innerHTML;
                    document.getElementById('popup-content').innerHTML = eventDetails;
                    document.getElementById('popup-overlay').style.display = 'block';
                    document.getElementById('popup').style.display = 'block';
                });
            });

            document.querySelectorAll('.event-link').forEach(function(link) {
                link.addEventListener('click', function(event) {
                    event.stopPropagation();
                });
            });

            document.getElementById('close-btn').addEventListener('click', function() {
                document.getElementById('popup-overlay').style.display = 'none';
                document.getElementById('popup').style.display = 'none';
            });

            document.getElementById('popup-overlay').addEventListener('click', function() {
                document.getElementById('popup-overlay').style.display = 'none';
                document.getElementById('popup').style.display = 'none';
            });
        });
    </script>
</body>
</html>
"""

# Save the HTML content to a file
with open('index.html', 'w', encoding='utf-8') as file:
    file.write(html_content)