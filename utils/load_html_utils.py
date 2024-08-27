# load_html_utils.py

from datetime import datetime, timedelta, timezone
import pytz
import re

# List of group_ids of extra events
extra_event_group_ids = [
    265,    # Los Gatos Bicycle Racing Club
    908336  # Ruekn Bicci Gruppo (Southern California)
]

# 本地时区
local_tz = pytz.timezone('America/Los_Angeles')  # Change this to your local time zone


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

def gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, route_url, source_group_name):
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

    # Detail page for the event
    popup_div += f"""
                </div>
                <div class="event-title">{event['title']}</div>
            </div>
            <p class="event-description">{event_description}</p>
    """
    # If the event has a event_picture_url URL, display it with link to source_url
    if 'event_picture_url' in event and event['event_picture_url'].startswith('http'):
        popup_div += f"""
            <a href="{source_event_url}" target="_blank" class="event-link">
                <img src="{event['event_picture_url']}" alt="Event Image" width="100%">
            </a>
        """
    popup_div += f"""
            <a href="{route_url}" target="_blank" class="event-link">
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
        # Find the event_area by matching the GPS coordinates with the area boundaries: south california, north california
        event_area = ""
        if gps_coordinates_str:
            gps_coordinates = [float(coord) for coord in gps_coordinates_str.split(', ')]
            if 35 <= gps_coordinates[0] <= 40 and -123.3 <= gps_coordinates[1] <= -119.5:
                event_area = '北加'
            elif 32 <= gps_coordinates[0] <= 35 and -120 <= gps_coordinates[1] <= -114:
                event_area = '南加'

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
        route_url = event.get('strava_url', "")
        if route_url == "" and 'source_url' in event and event['source_url'].startswith('http'):
            route_url = event['source_url']
        source_event_url = event.get('source_url', "")
        if source_event_url == "" and route_url != "":
            source_event_url = route_url
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
        events_div += gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, route_url, source_group_name)
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
        if event_area:
            events_div += f"""
                    <div class="area-box">{event_area}</div>
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
                <a href="{route_url}" target="_blank" class="event-link">
                    <img src="{event['route_map_url']}" alt="Route Image" width="100%">
                </a>
            </div>
            <div class="event-section">
                <div class="event-title">{event['title']}</div> <br>
                <div class="event-description">发起人: {event['organizer']}</div> <br>
                <div class="event-description">活动来源: <a href="{source_event_url}" target="_blank" class="event-link">{source_group_name}</a></div>
        """
        # If the event has a event_picture_url URL, display it with link to source_url
        if 'event_picture_url' in event and event['event_picture_url'].startswith('http'):
            events_div += f"""
                <a href="{source_event_url}" target="_blank" class="event-link">
                    <img src="{event['event_picture_url']}" alt="Event Image" width="100%">
                </a>
        """
        events_div += f"""
            </div>
        </div>
        """
    return events_div



# Define custom icons for different event types
custom_icons = {
    "upcoming": "http://maps.google.com/mapfiles/ms/icons/green-dot.png",
    "planning": "http://maps.google.com/mapfiles/ms/icons/yellow-dot.png",
    "past": "http://maps.google.com/mapfiles/ms/icons/gray-dot.png",
    "others": "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
}

def gen_gmp_advanced_marker_for_events_from_list(event_list, event_time_type="upcoming"):
    events_marker=""
    for event in event_list:
        event_type = "extra-event" if event['source_group_id'] in extra_event_group_ids else "selected-event"
        event_time_utc = event['event_time_utc'].replace(tzinfo=pytz.utc)
        event_time_local = event_time_utc.astimezone(local_tz)
        month_str = event_time_local.strftime('%b').upper()
        day_str = event_time_local.strftime('%d')
        event_title=event['title']
        event_id=f"event-{event['_id']}"
        gps_coordinates_str = event['gps_coordinates']
        if gps_coordinates_str=="":
            continue
        gps_coordinates_str='{ lat: ' + gps_coordinates_str.replace(',',', lng: ') + ' }'

        # Determine the color based on the event_time_type
        icon_url = custom_icons.get(event_time_type, custom_icons["others"])

        events_marker += f"""
            {'{'}
                title: "{month_str} {day_str}: {event_title}",
                position: {gps_coordinates_str},
                id: "{event_id}",
                icon: "{icon_url}"
            {'}'},
        """
    return events_marker
