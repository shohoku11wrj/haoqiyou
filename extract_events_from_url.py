import json
import os
import re
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Any, Dict, Iterable, List, Optional, Tuple

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up OpenAI API key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Calculate the cutoff date (two weeks ago from today)
CUTOFF_DATE = datetime.now() - timedelta(weeks=2)

_GARMIN_ROUTE_CACHE: Dict[str, bytes] = {}
_RIDEWITHGPS_HEADERS = {
    "User-Agent": os.getenv(
        "RIDEWITHGPS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ),
    "Accept": "application/json, text/plain, */*",
}


def extract_from_connect_garmin(course_url: str) -> bytes:
    """Fetch the encoded route polyline from a Garmin Connect course page.

    This helper mirrors Garmin's frontend requests so it can run in simple CLI
    contexts. It keeps a tiny in-memory cache to avoid duplicate fetches when
    the same course is requested repeatedly.

    The Garmin API often requires an authenticated session. If the call returns
    an empty payload, an informative error is raised so the caller can provide
    the needed cookies (for example, via the GARMIN_CONNECT_COOKIE environment
    variable).

    Args:
        course_url: Public Garmin Connect course URL.

    Returns:
        The encoded polyline as bytes. The bytes value is printed before being
        returned so the caller sees the binary representation immediately in the
        CLI output, as requested.
    """

    if not course_url:
        raise ValueError("A Garmin course URL is required")

    match = re.search(r"/course/(\d+)", course_url)
    if not match:
        raise ValueError(f"Unable to parse course id from URL: {course_url}")

    course_id = match.group(1)

    if course_id in _GARMIN_ROUTE_CACHE:
        poly_bytes = _GARMIN_ROUTE_CACHE[course_id]
        print(poly_bytes)
        return poly_bytes

    session = requests.Session()

    base_headers = {
        "User-Agent": os.getenv(
            "GARMIN_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        session.get(course_url, headers=base_headers, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Garmin course page {course_url}") from exc

    _apply_cookie_overrides(session)

    api_headers = {
        "User-Agent": base_headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Referer": course_url,
        "Origin": "https://connect.garmin.com",
        "NK": "NT",
        "X-app-ver": os.getenv("GARMIN_URL_BUST", "5.17.3.2"),
        "X-lang": os.getenv("GARMIN_LOCALE", "en-US"),
    }

    api_url = f"https://connect.garmin.com/modern/proxy/course-service/course/{course_id}"

    try:
        response = session.get(api_url, headers=api_headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Garmin course data for {course_id}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Garmin course API returned non-JSON data") from exc

    if not payload:
        raise ValueError(
            "Garmin course API returned an empty payload. Authentication is likely required."
        )

    polyline = _extract_polyline_from_payload(payload)
    if not polyline:
        raise ValueError("Unable to locate polyline data in Garmin payload")

    poly_bytes = polyline.encode("utf-8")
    _GARMIN_ROUTE_CACHE[course_id] = poly_bytes
    print(poly_bytes)
    return poly_bytes


def extract_route_polygon_from_ridewithgps(route_url: str) -> str:
    """Fetch and encode a Ride with GPS route as a Google polyline string."""

    if not route_url:
        raise ValueError("A Ride with GPS route URL is required")

    json_url = _build_ridewithgps_json_url(route_url)

    try:
        response = requests.get(json_url, headers=_RIDEWITHGPS_HEADERS, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Ride with GPS route data from {json_url}") from exc

    if response.status_code in {404, 403} or "json" not in response.headers.get(
        "Content-Type", ""
    ).lower():
        alt_url = _ensure_query_parameter(json_url, "format", "json")
        if alt_url != json_url:
            try:
                response = requests.get(alt_url, headers=_RIDEWITHGPS_HEADERS, timeout=30)
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Failed to load Ride with GPS route data from {alt_url}"
                ) from exc
            json_url = alt_url

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Ride with GPS route data from {json_url}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Ride with GPS route endpoint returned non-JSON data") from exc

    coords = _extract_ridewithgps_coordinates(payload)
    if not coords:
        raise ValueError("Unable to locate coordinate data in Ride with GPS payload")

    return _encode_polyline(coords)


def _build_ridewithgps_json_url(route_url: str) -> str:
    parsed = urlparse(route_url)

    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "ridewithgps.com"
    path = parsed.path.rstrip("/")

    if not path:
        raise ValueError(f"Invalid Ride with GPS route URL: {route_url}")

    if not path.endswith(".json"):
        path = f"{path}.json"

    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _ensure_query_parameter(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)

    updated = dict(query_pairs)
    if updated.get(key) == value:
        return url

    updated[key] = value
    new_query = urlencode(updated, doseq=True)

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def _extract_ridewithgps_coordinates(payload: Any) -> List[Tuple[float, float]]:
    """Traverse the Ride with GPS payload to collect latitude/longitude pairs."""

    queue: deque[Any] = deque([payload])

    while queue:
        current = queue.popleft()

        if isinstance(current, dict):
            # GeoJSON LineString format
            if current.get("type") == "LineString" and isinstance(
                current.get("coordinates"), list
            ):
                coords = _coerce_coordinate_sequence(current["coordinates"])
                if coords:
                    return coords

            for key, value in current.items():
                lowered = key.lower()
                if lowered in {
                    "track_points",
                    "trackpoints",
                    "points",
                    "coordinates",
                    "course_points",
                }:
                    coords = _coerce_coordinate_sequence(value)
                    if coords:
                        return coords
                elif lowered == "route_path" and isinstance(value, dict):
                    coords = _coerce_coordinate_sequence(value.get("coordinates"))
                    if coords:
                        return coords
                queue.append(value)
        elif isinstance(current, list):
            # Some payloads nest the interesting dict inside singleton lists.
            queue.extend(current)

    return []


def _coerce_coordinate_sequence(data: Any) -> List[Tuple[float, float]]:
    """Convert various coordinate point representations into (lat, lon) tuples."""

    if isinstance(data, dict):
        # Allow nested structures like {"coordinates": [...]}
        nested = data.get("coordinates") if "coordinates" in data else None
        if nested is not None:
            return _coerce_coordinate_sequence(nested)
        nested = data.get("points") if "points" in data else None
        if nested is not None:
            return _coerce_coordinate_sequence(nested)
        return []

    if not isinstance(data, list):
        return []

    coords: List[Tuple[float, float]] = []

    for entry in data:
        lat_lon: Optional[Tuple[float, float]] = None

        if isinstance(entry, dict):
            lat_lon = _latlon_from_dict(entry)
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            lat_lon = _latlon_from_sequence(entry)

        if not lat_lon:
            continue

        if coords and lat_lon == coords[-1]:
            continue

        coords.append(lat_lon)

    return coords


def _latlon_from_dict(entry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    keys = {key.lower(): key for key in entry.keys()}

    lat_key: Optional[str] = None
    for candidate in ("lat", "latitude", "y"):
        if candidate in keys:
            lat_key = keys[candidate]
            break

    lon_key: Optional[str] = None
    for candidate in ("lon", "lng", "longitude", "x"):
        if candidate in keys:
            lon_key = keys[candidate]
            break

    if lat_key is None or lon_key is None:
        # Some payload formats use "a"/"b" or "1"/"0" style keys; attempt detection.
        lat_key, lon_key = _guess_lat_lon_keys(entry)

    if lat_key is None or lon_key is None:
        return None

    try:
        lat = float(entry[lat_key])
        lon = float(entry[lon_key])
    except (TypeError, ValueError):
        return None

    return lat, lon


def _guess_lat_lon_keys(entry: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    lat_candidate: Optional[str] = None
    lon_candidate: Optional[str] = None

    for key, value in entry.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        if -90.0 <= numeric <= 90.0 and lat_candidate is None:
            lat_candidate = key
        elif -180.0 <= numeric <= 180.0 and lon_candidate is None:
            lon_candidate = key

    return lat_candidate, lon_candidate


def _latlon_from_sequence(entry: Iterable[Any]) -> Optional[Tuple[float, float]]:
    iterator = list(entry)
    if len(iterator) < 2:
        return None

    first, second = iterator[0], iterator[1]

    try:
        first_f = float(first)
        second_f = float(second)
    except (TypeError, ValueError):
        return None

    if -90.0 <= first_f <= 90.0 and -180.0 <= second_f <= 180.0:
        return first_f, second_f

    if -180.0 <= first_f <= 180.0 and -90.0 <= second_f <= 90.0:
        return second_f, first_f

    return None


def _apply_cookie_overrides(session: requests.Session) -> None:
    """Inject optional cookies provided via environment variables."""

    cookie_env = os.getenv("GARMIN_CONNECT_COOKIE", "").strip()
    if cookie_env:
        cookie_dict: Dict[str, str] = {}
        for part in cookie_env.split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key and value:
                cookie_dict[key] = value
        if cookie_dict:
            session.cookies.update(cookie_dict)

    guid = os.getenv("GARMIN_SSO_GUID")
    if guid and not session.cookies.get("GARMIN-SSO-GUID"):
        session.cookies.set("GARMIN-SSO-GUID", guid)


def _extract_polyline_from_payload(payload: Any) -> Optional[str]:
    """Search the Garmin payload for an encoded polyline or assemble one."""

    queue: deque[Any] = deque([payload])

    while queue:
        current = queue.popleft()

        if isinstance(current, dict):
            for key, value in current.items():
                lowered = key.lower()
                if "polyline" in lowered and isinstance(value, str) and value:
                    return value
                if lowered == "polylinedto" and isinstance(value, list):
                    encoded = _encode_from_points(value)
                    if encoded:
                        return encoded
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)

    return None


def _encode_from_points(points: Iterable[Any]) -> Optional[str]:
    """Encode point dictionaries (latitude / longitude) into a polyline."""

    coords = []
    for point in points:
        if not isinstance(point, dict):
            continue
        lat = point.get("latitude") or point.get("lat")
        lon = point.get("longitude") or point.get("lon")
        if lat is None or lon is None:
            continue
        try:
            coords.append((float(lat), float(lon)))
        except (TypeError, ValueError):
            continue

    if not coords:
        return None

    return _encode_polyline(coords)


def _encode_polyline(coordinates: Iterable[Iterable[float]], precision: int = 5) -> str:
    """Encode coordinates using Google's polyline algorithm."""

    factor = 10 ** precision
    encoded_chars: list[str] = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in coordinates:
        lat_i = int(round(lat * factor))
        lng_i = int(round(lng * factor))

        encoded_chars.append(_encode_polyline_value(lat_i - prev_lat))
        encoded_chars.append(_encode_polyline_value(lng_i - prev_lng))

        prev_lat = lat_i
        prev_lng = lng_i

    return "".join(encoded_chars)


def _encode_polyline_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunk_chars: list[str] = []
    while value >= 0x20:
        chunk_chars.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunk_chars.append(chr(value + 63))
    return "".join(chunk_chars)


def extract_route_polygon_from_local_html(html_path: str = "storage/garmin_route.html") -> str:
    """Extract a Garmin route from a saved HTML snippet and return a polyline.

    The helper first looks for an already-encoded polyline within the HTML
    (e.g. a ``summaryPolyline`` field). If that is unavailable it falls back to
    reconstructing the route from the SVG ``<path>`` element. When map bounds are
    present they are used to translate the SVG pixel coordinates into latitude /
    longitude values; otherwise the coordinates are normalised into a unit square
    so that the caller still receives a valid (albeit relative) polyline.

    Args:
        html_path: Filesystem path to the saved Garmin HTML snippet.

    Returns:
        A Google encoded polyline string representing the route geometry.

    Raises:
        FileNotFoundError: When ``html_path`` does not exist.
        ValueError: If the HTML does not contain sufficient data to rebuild the
            route geometry.
    """

    html_file = Path(html_path)
    if not html_file.exists():
        raise FileNotFoundError(f"Garmin route HTML not found: {html_path}")

    raw_html = html_file.read_text(encoding="utf-8")

    encoded = _extract_summary_polyline_from_html(raw_html)
    if encoded:
        return encoded

    soup = BeautifulSoup(raw_html, "html.parser")
    pixel_points = _extract_svg_points(soup)
    if not pixel_points:
        raise ValueError("Unable to locate SVG path data for route in the provided HTML")

    bounds = _extract_bounds_from_html(raw_html)
    if bounds:
        latlon_points = _remap_pixels_to_wgs84(pixel_points, bounds)
    else:
        latlon_points = _normalize_pixels_to_unit_route(pixel_points)
    if not latlon_points:
        raise ValueError("Failed to convert SVG route coordinates to geographic coordinates")

    print(latlon_points)
    return _encode_polyline(latlon_points)


def _extract_summary_polyline_from_html(raw_html: str) -> Optional[str]:
    """Return the first embedded polyline string found in the HTML, if any."""

    candidates = [
        r'"summaryPolyline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"summary_polyline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"polyline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
    ]

    for pattern in candidates:
        match = re.search(pattern, raw_html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        try:
            return json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            continue

    return None


def _extract_bounds_from_html(raw_html: str) -> Optional[Dict[str, float]]:
    """Pull north/south/east/west bounds from Garmin's HTML payload."""

    # Pattern for northEast / southWest blocks.
    ne_sw_pattern = re.compile(
        r'"northEast"\s*:\s*{[^}]*?(?:"lat(?:itude)?"\s*:\s*(?P<ne_lat>-?\d+(?:\.\d+)?)).*?'
        r'(?:"lon(?:gitude)?"|"lng")\s*:\s*(?P<ne_lon>-?\d+(?:\.\d+)?)[^}]*?}\s*,\s*'
        r'"southWest"\s*:\s*{[^}]*?(?:"lat(?:itude)?"\s*:\s*(?P<sw_lat>-?\d+(?:\.\d+)?)).*?'
        r'(?:"lon(?:gitude)?"|"lng")\s*:\s*(?P<sw_lon>-?\d+(?:\.\d+)?)[^}]*?}',
        flags=re.IGNORECASE | re.DOTALL,
    )

    match = ne_sw_pattern.search(raw_html)
    if match:
        return {
            "north": float(match.group("ne_lat")),
            "south": float(match.group("sw_lat")),
            "east": float(match.group("ne_lon")),
            "west": float(match.group("sw_lon")),
        }

    bounding_box_pattern = re.compile(
        r'"boundingBox"\s*:\s*{[^}]*?'
        r'"lowerLeft"\s*:\s*{[^}]*?"lat(?:itude)?"\s*:\s*(?P<ll_lat>-?\d+(?:\.\d+)?).*?'
        r'(?:"lon(?:gitude)?"|"lng")\s*:\s*(?P<ll_lon>-?\d+(?:\.\d+)?)[^}]*?}\s*,\s*'
        r'"upperRight"\s*:\s*{[^}]*?"lat(?:itude)?"\s*:\s*(?P<ur_lat>-?\d+(?:\.\d+)?).*?'
        r'(?:"lon(?:gitude)?"|"lng")\s*:\s*(?P<ur_lon>-?\d+(?:\.\d+)?)[^}]*?}',
        flags=re.IGNORECASE | re.DOTALL,
    )

    match = bounding_box_pattern.search(raw_html)
    if match:
        return {
            "north": float(match.group("ur_lat")),
            "south": float(match.group("ll_lat")),
            "east": float(match.group("ur_lon")),
            "west": float(match.group("ll_lon")),
        }

    # Pattern for explicit bounds formatted with cardinal keys.
    cardinal_pattern = re.compile(
        r'"north"\s*:\s*(?P<north>-?\d+(?:\.\d+)?).*?'
        r'"south"\s*:\s*(?P<south>-?\d+(?:\.\d+)?).*?'
        r'"east"\s*:\s*(?P<east>-?\d+(?:\.\d+)?).*?'
        r'"west"\s*:\s*(?P<west>-?\d+(?:\.\d+)?).*?}',
        flags=re.IGNORECASE | re.DOTALL,
    )

    match = cardinal_pattern.search(raw_html)
    if match:
        return {
            "north": float(match.group("north")),
            "south": float(match.group("south")),
            "east": float(match.group("east")),
            "west": float(match.group("west")),
        }

    return None


def _extract_svg_points(soup: BeautifulSoup) -> List[Tuple[float, float]]:
    """Parse all SVG paths that describe the rendered route."""

    seen_paths: set[str] = set()
    points: List[Tuple[float, float]] = []

    def is_route_path(path_tag: Any) -> bool:
        stroke = (path_tag.get("stroke") or "").lower()
        cls = path_tag.get("class") or ""
        return "leaflet-interactive" in cls and stroke in {"#2a88e6", "#007bf6", "#ff6f00"}

    for path_tag in soup.find_all("path"):
        d = path_tag.get("d")
        if not d or d in seen_paths:
            continue
        if not is_route_path(path_tag):
            # Also accept the thicker shadow path if route coloured path missing.
            if "CourseMap_polyLineNoHover" not in (path_tag.get("class") or ""):
                continue
        seen_paths.add(d)
        segment_points = _parse_svg_path_points(d)
        for point in segment_points:
            if not points or point != points[-1]:
                points.append(point)

    return points


def _parse_svg_path_points(path_d: str) -> List[Tuple[float, float]]:
    """Convert an SVG path comprised of ``M``/``L`` commands into points."""

    matches = re.findall(r'([ML])\s*(-?\d+(?:\.\d+)?)\s*(-?\d+(?:\.\d+)?)', path_d)
    if not matches:
        return []

    parsed_points: List[Tuple[float, float]] = []
    for command, x_str, y_str in matches:
        if command.upper() not in {"M", "L"}:
            continue
        parsed_points.append((float(x_str), float(y_str)))

    return parsed_points


def _remap_pixels_to_wgs84(
    points: List[Tuple[float, float]], bounds: Dict[str, float]
) -> List[Tuple[float, float]]:
    """Interpolate pixel coordinates so they align with geographic bounds."""

    if not points:
        return []

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if max_x == min_x or max_y == min_y:
        return []

    north = bounds["north"]
    south = bounds["south"]
    east = bounds["east"]
    west = bounds["west"]

    lon_span = east - west
    lat_span = north - south

    if lon_span == 0 or lat_span == 0:
        return []

    latlon_points: List[Tuple[float, float]] = []
    for x, y in points:
        lon_ratio = (x - min_x) / (max_x - min_x)
        lat_ratio = (y - min_y) / (max_y - min_y)

        lon = west + lon_span * lon_ratio
        lat = north - lat_span * lat_ratio
        latlon_points.append((lat, lon))

    return latlon_points


def _normalize_pixels_to_unit_route(
    points: List[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """Scale pixel coordinates into a unit square fallback representation."""

    if not points:
        return []

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if max_x == min_x or max_y == min_y:
        return []

    normalized: List[Tuple[float, float]] = []
    for x, y in points:
        lon_ratio = (x - min_x) / (max_x - min_x)
        lat_ratio = (y - min_y) / (max_y - min_y)
        normalized.append((1.0 - lat_ratio, lon_ratio))

    return normalized

def extract_detail_feilds(html_content):
    fields_prompt_map = {
        'organizer: ': '<strong>Ride Leader</strong>: John<strong>. Expected Value: John',
        'meetup_time: ': 'The start time of the event. For example: given the text of "Time:  Saturday, gather at 9am. rolling by 9:15am". Expected Value: 09:00',
    }
    prompt = f"Extract the following fields ${fields_prompt_map.keys} about riding event from the following text:\n```\n{html_content}\n```\nHere are some examples of the fields and their context to extract:\n"
    for field, context in fields_prompt_map.items():
        prompt += f"Field: {field}, Context: {context}\n"
    prompt += '\nThe output should be json format, for example:\n{"organizer": "John", "meetup_time": "09:00"}\n'
    prompt += '\nFor each riding event, just generate the ${fields_prompt_map.keys} fields.\n'

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        # response = genai.generate_text(
        #     model="models/gemini-1.5-flash-001",
        #     prompt=prompt,
        #     temperature=1,
        #     max_output_tokens=100
        # )
        # Process the response
        if response.text:
            print("response", response.text)
        else:
            # Handle potential errors gracefully
            print(f"Error: {response.error}")
        # Example response: response ```json\n{"organizer": "John", "meetup_time": "09:00"}\n```
        ai_response = response.text.lstrip('```json').rstrip('```').strip()
        return ai_response
        # return {
        #     'organizer': ai_response.split('organizer: ')[1].split('\n')[0].strip(),
        #     'meetup_time': ai_response.split('meetup_time: ')[1].strip()
        # }
    except Exception as e:
        print("Error extracting details: ", e)
        return {}


def fetch_events(url):
    response = requests.get(url)
    response.raise_for_status()  # Ensure we notice bad responses
    return response.text

def parse_single_event(event):
    html_content = fetch_events(event['source_url'])
    soup = BeautifulSoup(html_content, 'html.parser')
    # Extract event details
    description_tag = soup.find('div', class_='sqs-html-content')
    time_tag = description_tag.find('strong', text='Time: ')
    organizer_tag = description_tag.find('strong', text='Ride Leader')
    # the organize name is in a text right after the organizer tag
    # sometimes start with ": " or " - ", so we need to strip the leading characters
    organizer_name = organizer_tag.next_sibling.lstrip(':').lstrip('-').strip() if organizer_tag else 'Alto Velo members'
    # the href should start with "https://www.strava.com/routes/"
    # for example" <a href="https://www.strava.com/routes/3264481791722414714" target="_blank"><strong>&nbsp;OLH &amp; W-OLH + Joaquin</strong></a>
    # route_map_tag = description_tag.find('a', href=True, text=True)
    # the meet up location tag should be a link to google maps
    # for example: <a href="https://maps.app.goo.gl/emgD6hdD9fLTaJch6"><strong><em>Summit Bicycles</em>&nbsp;</strong></a>
    # meet_up_location_tag = description_tag.find('a', href=True, text=True)
    # event.date sample: 8/21/24, event.time sample: 9am

    # Extract specific details from the description
    date_time_str = ''
    start_location = ''
    strava_url = ''
    ride_leader = ''

    if description_tag:
        for p in description_tag.find_all('p'):
            text = p.get_text(strip=True)
            if 'Time:' in text:
                date_time_str = text.split('Time:')[1].strip()
            if 'Start:' in text:
                start_location = p.find('a')['href'] if p.find('a') and 'maps.app.goo.gl' in p.find('a')['href'] else text.split('Start:')[1].strip()
            if 'Route Link:' in text or ('strava.com/routes' in p.find('a')['href'] if p.find('a') else ''):
                strava_url = p.find('a')['href'] if p.find('a') and 'strava.com/routes' in p.find('a')['href'] else ''
            if 'Ride Leader' in text:
                ride_leader = text.split('Ride Leader:')[1].strip()

    # Extract the event details using AI
    detail_feilds = extract_detail_feilds(description_tag)
    # Example: ```json{"organizer": "John", "meetup_time": "09:00"}````
    print("Extracted details: ", detail_feilds.strip())
    # Parse the string to json
    detail_feilds = json.loads(detail_feilds)
    ride_leader = detail_feilds['organizer'] if 'organizer' in detail_feilds else ride_leader
    event_time_str = event['date'] + detail_feilds['meetup_time'] +':00.000-07:00'

    event_details = {
        'source_type': 'webpage',
        'source_event_id': {
            '$numberLong': '2024083109000001'  # Example ID, you may need to generate this dynamically
        },
        'source_group_id': {
            '$numberLong': '1047313'  # Alto Velo C Ride group ID
        },
        'description': '',
        'distance_meters': 0,
        'elevation_gain_meters': 0,
        'event_time_utc': {
            '$date': event_time_str
        },
        'gps_coordinates': '37.426627, -122.144647',  # Example coordinates, you may need to extract this dynamically
        'is_active': True,
        'meet_up_location': start_location,
        'organizer': detail_feilds['organizer'] if 'organizer' in detail_feilds else ride_leader,
        'strava_url': strava_url,
        'source_group_name': 'Alto Velo C Ride',
        'title': event['title'],
        'source_url': event['source_url']
    }

    return event_details

def parse_event_details(events_list):
    event_details_list = []
    for event in events_list:
        single_event_detail = parse_single_event(event)
        event_details_list.append(single_event_detail)
    return event_details_list

def parse_events(url):
    events = []
    html_content = fetch_events(url)
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = soup.find_all('article', class_='blog-single-column--container')
    for article in articles:
        title_tag = article.find('h1', class_='blog-title').find('a')
        date_tag = article.find('time', class_='blog-date')
        if title_tag and date_tag:
            event_title = title_tag.text.strip()
            event_date_str = date_tag.text.strip()
            event_date = datetime.strptime(event_date_str, '%m/%d/%y')
            
            # Stop parsing if the event date is earlier than the cutoff date
            if event_date < CUTOFF_DATE:
                continue

            event_url = 'https://www.altovelo.org' + title_tag['href']
            events.append({
                'title': event_title,
                'date': event_date_str,
                'source_url': event_url
            })
    
    return events

def main():
    #url = 'https://www.altovelo.org/c-ride'
    #events_list = parse_events(url)
    #event_details_list = parse_event_details(events_list)
    #print(event_details_list)
    #print(extract_from_connect_garmin("https://connect.garmin.com/modern/course/400017456"))
    # extract route from <g> element from garmin html
    #print(extract_route_polygon_from_local_html("storage/garmin_route.html"))
    # extract route from ridewithgps
    print(extract_route_polygon_from_ridewithgps("https://ridewithgps.com/routes/52796073"))


if __name__ == '__main__':
    main()
