# load_html_utils.py

from datetime import datetime, timedelta, timezone
import pytz
import re
import html

# List of group_ids of extra events
extra_event_group_ids = [
    265,      # Los Gatos Bicycle Racing Club
    908336,   # Ruekn Bicci Gruppo (Southern California)
    1047313,  # Alto Veto C Ride
]

DAY_OF_WEEK_MAP = {
    'Monday': '周一',
    'Tuesday': '周二',
    'Wednesday': '周三',
    'Thursday': '周四',
    'Friday': '周五',
    'Saturday': '周六',
    'Sunday': '周日'
}



def escape_attr(value):
    if value is None:
        return ""
    return html.escape(str(value), quote=True)

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


# 获取当前时间所在周的周一00:00AM时间, 切不能小于当前时间
def get_start_of_week():
    now = datetime.now(pytz.utc)  # 使用UTC时间
    start_of_week = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    if start_of_week <= now:
        start_of_week = start_of_week - timedelta(days=7)
    return start_of_week


def gen_event_detail_popup_div(event, event_time_str, day_of_week, month_str, day_str, year, gps_coordinates_str, distance_str, elevation_gain_str, source_event_url, route_url, source_group_name):
    # Convert URLs in the description to hyperlinks
    event_description = convert_urls_to_links(event['description'])
    day_of_week_str = DAY_OF_WEEK_MAP[day_of_week]
    popup_div = f"""
        <div id="event-{event['_id']}" style="display: none;">
            <div class="event-title-row">
                <div class="date-box">
                    <div class="date">{day_str}</div>
                    <div class="month">{month_str}</div>
                    <div class="day-of-week">{day_of_week_str}</div>
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
    if ('event_picture_url' in event and event['event_picture_url'].startswith('http'))\
        or ('event_picture_urls' in event and event['event_picture_urls'] and len(event['event_picture_urls']) == 1 and event['event_picture_urls'][0].startswith('http')):
        event_picture_url_0 = event['event_picture_url'] if 'event_picture_url' in event else event['event_picture_urls'][0]
        popup_div += f"""
            <a href="{source_event_url}" target="_blank" class="event-link">
                <img src="{event_picture_url_0}" alt="Event Image" width="100%">
            </a>
    """
    # If the event has multiple event_picture_urls, create a slideshow
    if 'event_picture_urls' in event and len(event['event_picture_urls']) > 1:
        popup_div += f"""
            <div class="slideshow-container">
                <div class="slides-wrapper" slides-length="{len(event['event_picture_urls'])}">
        """
        for i, img_url in enumerate(event['event_picture_urls']):

            popup_div += f"""
                    <div class="slide" data-index="{i}" style="{'block' if i == 0 else 'none'}">
                        <a href="{img_url}" target="_blank" class="event-link">
                            <img src="{img_url}" alt="Event Image {i+1}" class="slide-image">
                        </a>
                    </div>
            """
        # Add navigation buttons if there's more than one image
        picture_count = len(event['event_picture_urls'])
        if len(event['event_picture_urls']) > 1:
            popup_div += f"""
                </div>
                <button class="slide-nav prev" onclick="moveSlide(-1, {picture_count})">❮</button>
                <button class="slide-nav next" onclick="moveSlide(1, {picture_count})">❯</button>
                <div class="slide-dots">
            """
            for i in range(len(event['event_picture_urls'])):
                popup_div += f"""
                    <span class="dot" onclick="currentSlide({i}, {picture_count})"></span>
                """
            popup_div += """
                </div>
            """
        popup_div += """
            </div>
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

    # # Generate QR code for the event with URL: https://haoqiyou.info/?id=event-{event['_id']}
    # qr_code_url = f"https://haoqiyou.info/?id=event-{event['_id']}"
    # popup_div += f"""
    #     <p><strong>扫码查看活动:</strong></p>
    #     <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={qr_code_url}" alt="QR Code" width="150">
    # """

    popup_div += "</div>"
    return popup_div


def gen_div_for_events_from_list(events_list, event_type):
    events_div = ""
    for event in events_list:
        # 时间
        # Convert the event's event_time_utc from datetime.datetime to local time zone
        event_time_utc = event['event_time_utc'].replace(tzinfo=pytz.utc)
        event_time_local = event_time_utc.astimezone(local_tz)
        event_time_local_iso = event_time_local.isoformat()
        # 12-hour format with AM/PM
        event_time_str = event_time_local.strftime('%I:%M %p').lstrip('0')
        # Extract month and day separately for the date-box
        year = event_time_utc.year
        month_str = event_time_local.strftime('%b').upper()
        day_str = event_time_local.strftime('%d')
        day_of_week = event_time_local.strftime('%A')  # Full weekday name
        calendar_start_utc = event_time_utc.strftime('%Y%m%dT%H%M%SZ')
        calendar_end_utc = (event_time_utc + timedelta(hours=3)).strftime('%Y%m%dT%H%M%SZ')
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
        route_url = event.get('route_url', "")
        if route_url == "":
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
        <div class="event {event_class}" data-event-id="event-{event_id}" data-event-title="{escape_attr(event["title"])}" data-event-start="{calendar_start_utc}" data-event-end="{calendar_end_utc}" data-event-location="{escape_attr(event["meet_up_location"])}" data-event-source-url="{escape_attr(source_event_url)}">
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
                        <div class="date-relative" event-date="{event_time_local_iso}"></div>
        """
        if event_area:
            events_div += f"""
                    <div class="area-box">{event_area}</div>
            """

        if event_type == 'upcoming' or event_type == 'planning':
            events_div += f"""
                    <div class="area-calendar-separator"></div>
                    <div class="calendar-box" data-calendar-trigger="icon">
                        <span class="material-symbols-outlined calendar-icon" aria-hidden="true">calendar_add_on</span>
                    </div>
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
                <div data-event-id="event-{event_id}-route-polyline" style="display: none;">{event.get('route_polyline', '')}</div>
            </div>
            <div class="event-section">
                <div class="event-title">{event['title']}</div> <br>
                <div class="event-description">发起人: {event['organizer']}</div> <br>
                <div class="event-description">活动来源: <a href="{source_event_url}" target="_blank" class="event-link">{source_group_name}</a></div>
        """

        # If the event has a event_picture_url URL, display it with link to source_url
        if ('event_picture_url' in event and event['event_picture_url'].startswith('http'))\
            or ('event_picture_urls' in event and event['event_picture_urls'] and len(event['event_picture_urls']) == 1 and event['event_picture_urls'][0].startswith('http')):
            event_picture_url_0 = event['event_picture_url'] if 'event_picture_url' in event else event['event_picture_urls'][0]
            events_div += f"""
                <a href="{source_event_url}" target="_blank" class="event-link">
                    <img src="{event_picture_url_0}" alt="Event Image" width="100%">
                </a>
            """
        # If the event has multiple event_picture_urls, only display the first image
        if 'event_picture_urls' in event and len(event['event_picture_urls']) > 1:
            first_img_url = event['event_picture_urls'][0]
            events_div += f"""
                <a href="{source_event_url}" target="_blank" class="event-link">
                    <img src="{first_img_url}"  width="100%"></img>
                </a>
            """
    
        events_div += f"""
            </div>
        </div>
        """
    return events_div


# Define custom icons for different event types
CUSTOM_ICONS = {
    "upcoming": "http://maps.google.com/mapfiles/ms/icons/green-dot.png",
    "planning": "http://maps.google.com/mapfiles/ms/icons/blue-dot.png",
    "past": "http://maps.google.com/mapfiles/ms/icons/yellow-dot.png",
    "others": "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
}
GPS_OVERLAP_TOLERANCE = 0.03
GPS_SHIFTS = [[0, -GPS_OVERLAP_TOLERANCE], [GPS_OVERLAP_TOLERANCE, 0], [0, GPS_OVERLAP_TOLERANCE], [-GPS_OVERLAP_TOLERANCE, 0],
              [GPS_OVERLAP_TOLERANCE, -GPS_OVERLAP_TOLERANCE], [GPS_OVERLAP_TOLERANCE, GPS_OVERLAP_TOLERANCE],
              [-GPS_OVERLAP_TOLERANCE, GPS_OVERLAP_TOLERANCE], [-GPS_OVERLAP_TOLERANCE, -GPS_OVERLAP_TOLERANCE],]


def gen_gmp_advanced_marker_for_events_from_list(event_list, event_time_type="upcoming", overlapping_gps_coords=set()):
    events_markers = []
    for event in event_list:
        event_type = "extra-event" if event['source_group_id'] in extra_event_group_ids else "selected-event"
        event_time_utc = event['event_time_utc'].replace(tzinfo=pytz.utc)
        event_time_local = event_time_utc.astimezone(local_tz)
        month_str = event_time_local.strftime('%b').upper()
        day_str = event_time_local.strftime('%d')

        distance_km = event['distance_meters'] / 1000
        distance_str = f"{distance_km:.2f} km"
        
        event_title=event['title']
        event_id=f"event-{event['_id']}"
        gps_coordinates_str = event['gps_coordinates']
        if gps_coordinates_str=="":
            continue
        # reserve 5 digits after the decimal point
        gps_coordinates = [float(coord) for coord in gps_coordinates_str.split(', ')]

        # Determine the color based on the event_time_type
        icon_url = CUSTOM_ICONS.get(event_time_type, CUSTOM_ICONS["others"])

        event_marker = {
            'title': f"{month_str} {day_str}: {event_title}",
            'date_span': [month_str, day_str],
            'position': gps_coordinates,
            'id': event_id,
            'icon_url': icon_url,
            'event_time_type': event_time_type,
        }
        events_markers.append(event_marker)
    return events_markers


# Iterate the events to find those GPS coordinates that are close to each other (with tolerance of 0.0001),
# and save them in a set.
def get_overlapping_gps_coords(events_list):
    overlapping_gps_coords = set()
    for i in range(len(events_list)):
        gps_coordinates_str1 = events_list[i]['gps_coordinates']
        if gps_coordinates_str1 == '':
            continue
        gps_coordinates1 = [float(coord) for coord in gps_coordinates_str1.split(', ')]
        lat1, lon1 = gps_coordinates1
    
        overrlapped = False
        for detected_gps in overlapping_gps_coords:
            lat2, lon2 = detected_gps
            if abs(lat1 - lat2) < GPS_OVERLAP_TOLERANCE and abs(lon1 - lon2) < GPS_OVERLAP_TOLERANCE:
                overlapping_gps_coords.add((lat1, lon1))
                overrlapped = True
                break
        if overrlapped:
            continue

        for j in range(i + 1, len(events_list)):
            gps_coordinates_str2 = events_list[j]['gps_coordinates']
            if gps_coordinates_str2 == '':
                continue
            gps_coordinates2 = [float(coord) for coord in gps_coordinates_str2.split(', ')]
            lat2, lon2 = gps_coordinates2
            if abs(lat1 - lat2) < GPS_OVERLAP_TOLERANCE and abs(lon1 - lon2) < GPS_OVERLAP_TOLERANCE:
                overlapping_gps_coords.add((lat1, lon1))
    return overlapping_gps_coords


# Iterate the event_markers to find those GPS coordinates that are close to each other (with tolerance of 0.0001),
def insert_shift_to_event_markers(event_markers, overlapping_gps_coords):
    # sort event_markers by latitude in every interger unit, then longitude
    event_markers.sort(key=lambda x: (int(x['position'][0]), x['position'][1]))
    overlapped_gps_count_map = {}
    for event_marker in event_markers:
        lat, lng = event_marker.get('position')[0], event_marker.get('position')[1]
        gps_shift = [0, 0]
        for overlapped_gps in overlapping_gps_coords:
            if abs(lat - overlapped_gps[0]) < GPS_OVERLAP_TOLERANCE and abs(lng - overlapped_gps[1]) < GPS_OVERLAP_TOLERANCE:
                overlapped_gps_count = overlapped_gps_count_map.get(overlapped_gps, 0)
                gps_shift = GPS_SHIFTS[overlapped_gps_count % len(GPS_SHIFTS)]
                overlapped_gps_count_map[overlapped_gps] = overlapped_gps_count + 1
                break
        event_marker.update({'shift': gps_shift})


def serialize_event_markers_to_string(event_markers):
    # Serialize event_markers to string
    # """
    #     {'{'}
    #         title: "{month_str} {day_str}: {event_title}",
    #         position: {gps_coordinates},
    #         shift: {gps_shift},
    #         id: "{event_id}",
    #         icon_url: "{icon_url}"
    #     {'}'},
    # """
    map_content = ''
    for event_marker in event_markers:
        map_content += f"""
        {{
            title: "{event_marker['title']}",
            date_span: {{ month: "{event_marker['date_span'][0]}", day: "{event_marker['date_span'][1]}" }},
            position: {{ lat: {event_marker['position'][0]}, lng: {event_marker['position'][1]} }},
            shift: {event_marker['shift']},
            id: "{event_marker['id']}",
            icon_url: "{event_marker['icon_url']}",
            event_time_type: "{event_marker['event_time_type']}"
        }},
        """
    return map_content
