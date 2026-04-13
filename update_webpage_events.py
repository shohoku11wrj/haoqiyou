"""Download and extract recent Alto Velo events from the saved webpage HTML."""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import pytz
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
WEBPAGE_HTML_PATH = STORAGE_DIR / "webpage.html"
EVENTS_JS_PATH = STORAGE_DIR / "events.js"
UTILS_DIR = ROOT_DIR / "utils"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from extract_route_from_garmin import extract_route_from_garmin
from extract_route_from_ridewithgps import extract_route_from_ridewithgps
from extract_route_from_strava import extract_route_from_strava
from event_storage import (
    DEFAULT_EVENTS_FILE,
    load_events_for_runtime,
    normalize_event_for_runtime,
    save_events_to_storage,
)


ALTOVELO_EVENTS_URL = "https://www.altovelo.org/a-ride"
REQUEST_TIMEOUT_SECONDS = 60
RECENT_DAYS = 14
PACIFIC_TZ = pytz.timezone("America/Los_Angeles")
EVENT_DETAIL_TIMEOUT_SECONDS = 60

_TIME_PATTERN = re.compile(
    r"\b(\d{1,2}[:\.]?\d{0,2})\s*((?:A|P)\.?M\.?)(?![A-Za-z])",
    re.IGNORECASE,
)
_DISTANCE_PATTERN = re.compile(
    r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(miles?|mi|kilometers?|km)\b",
    re.IGNORECASE,
)
_LOCATION_PATTERN = re.compile(
    r"(?i)(start(?:/end)?|meet(?:ing)?(?: location)?):\s*([^\n]+)"
)
_STARTING_AT_PATTERN = re.compile(r"(?i)starting at\s+(.+)")
_GPS_PATTERN = re.compile(r"(-?\d{2}\.\d{3,}),\s*(-?\d{2,3}\.\d{3,})")
_URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")
_ROUTE_METRICS_PATTERN = re.compile(
    r"~?(?P<distance>\d+(?:,\d{3})*(?:\.\d+)?k?)\s*"
    r"(?P<distance_unit>miles?|mi|kilometers?|km)\b"
    r"(?:\s*[/,]\s*|\s+-\s+|\s+)"
    r"~?(?P<elevation>\d+(?:,\d{3})*(?:\.\d+)?k?)\s*"
    r"(?P<elevation_unit>feet|foot|ft|meters?|m)\b",
    re.IGNORECASE,
)
_RIDE_LEADER_PATTERN = re.compile(r"(?i)ride leader:\s*(.*)")
_RIDEWITHGPS_ROUTE_PATTERN = re.compile(r"https?://(?:www\.)?ridewithgps\.com/routes/\d+\S*")
_GARMIN_ROUTE_PATTERN = re.compile(
    r"https?://connect\.garmin\.com/(?:modern|app)/course/?\d+\S*",
    re.IGNORECASE,
)
_STRAVA_ROUTE_PATTERN = re.compile(r"https?://(?:www\.)?strava\.com/routes/\d+\S*")
_STRAVA_SEGMENT_PATTERN = re.compile(r"https?://(?:www\.)?strava\.com/segments/\d+\S*")

DEFAULT_MEET_LOCATION = "Summit Bicycles, 392 California Ave, Palo Alto, CA"
DEFAULT_MEET_GPS = "37.42797, -122.14508"
KNOWN_LOCATIONS = {
    "summit bicycles": DEFAULT_MEET_GPS,
    "392 california ave": DEFAULT_MEET_GPS,
}
CANONICAL_LOCATION_ALIASES = {
    "summit bicycles, palo alto": "Summit Bicycles, Palo Alto",
    "summit bikes palo alto": "Summit Bicycles, Palo Alto",
    "summit bikes in palo alto": "Summit Bicycles, Palo Alto",
    "summit bicycles palo alto": "Summit Bicycles, Palo Alto",
    "summit bicycles, los gatos": "Summit Bicycles, Los Gatos",
    "summit bikes los gatos": "Summit Bicycles, Los Gatos",
    "summit bikes in los gatos": "Summit Bicycles, Los Gatos",
    "summit bicycles los gatos": "Summit Bicycles, Los Gatos",
}
_LABEL_TERMINATORS = {
    "route",
    "summary",
    "start",
    "start/end",
    "time",
    "ride etiquette",
    "ride leader",
    "regroups/stops",
    "pace",
    "ride stats",
}



def download_altovelo_webpage(url: str = ALTOVELO_EVENTS_URL) -> Path:
    """Download the Alto Velo events page HTML and persist it under storage/webpage.html."""

    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    WEBPAGE_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEBPAGE_HTML_PATH.write_text(response.text, encoding="utf-8")
    return WEBPAGE_HTML_PATH


def load_saved_webpage(path: Path = WEBPAGE_HTML_PATH) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Saved webpage HTML not found at {path}. Run download_altovelo_webpage() first."
        )
    return path.read_text(encoding="utf-8")


def _parse_display_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


_TITLE_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")


def _derive_event_date(title: str, fallback_year: int) -> Optional[datetime]:
    match = _TITLE_DATE_RE.search(title)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    year_str = match.group(3)
    if year_str:
        year = int(year_str)
        if year < 100:
            year += 2000
    else:
        year = fallback_year
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _extract_article_date(article: Tag) -> Optional[datetime]:
    time_el = article.select_one("time.blog-date")
    if not time_el or not time_el.text:
        return None
    return _parse_display_date(time_el.text)


def extract_recent_events_from_html(html: str, *, limit: Optional[int] = None) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.blog-single-column--container")
    cutoff = (datetime.now(PACIFIC_TZ) - timedelta(days=RECENT_DAYS)).date()
    events: List[Dict[str, str]] = []

    for article in articles:
        title_link = article.select_one("h1.blog-title a")
        if not title_link:
            continue
        event_name = title_link.get_text(strip=True)
        href = title_link.get("href") or ""
        event_url = urljoin(ALTOVELO_EVENTS_URL, href)

        article_date = _extract_article_date(article)
        fallback_year = article_date.year if article_date else datetime.now(PACIFIC_TZ).year
        event_dt = _derive_event_date(event_name, fallback_year)
        if event_dt is None:
            event_dt = article_date
        if event_dt is None:
            continue

        if event_dt.date() < cutoff:
            continue

        events.append(
            {
                "event_name": event_name,
                "event_date": event_dt.strftime("%Y-%m-%d"),
                "event_url": event_url,
            }
        )

    events.sort(
        key=lambda evt: datetime.strptime(evt["event_date"], "%Y-%m-%d"),
        reverse=True,
    )

    if limit is not None:
        return events[:limit]
    return events


def fetch_event_detail_html(event_url: str) -> str:
    response = requests.get(event_url, timeout=EVENT_DETAIL_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _extract_text_content(soup: BeautifulSoup) -> str:
    body = soup.select_one("article") or soup
    return body.get_text("\n", strip=True)


def _extract_start_time(text_lines: List[str], text: str) -> str:
    labeled_time = _extract_labeled_value(text_lines, ("time",))
    if labeled_time:
        match = _TIME_PATTERN.search(labeled_time)
        if match:
            return match.group(0)

    for index, line in enumerate(text_lines):
        lower_line = line.lower()
        if "time" not in lower_line and "meet" not in lower_line:
            continue
        match = _TIME_PATTERN.search(line)
        if match:
            return match.group(0)
        if index + 1 < len(text_lines):
            next_match = _TIME_PATTERN.search(text_lines[index + 1])
            if next_match:
                return next_match.group(0)

    match = _TIME_PATTERN.search(text)
    return match.group(0) if match else ""


def _extract_location(text_lines: List[str]) -> str:
    labeled_start = _extract_labeled_value(text_lines, ("start", "start/end"))
    if labeled_start:
        location = re.split(r"\.\s*(?:Meet|Roll|Leave)\b", labeled_start, maxsplit=1)[0].strip()
        location = re.sub(r"^\:\s*", "", location).strip()
        if location:
            return _normalize_meet_location(location)

    for line in text_lines:
        match = _LOCATION_PATTERN.search(line)
        if match:
            location = match.group(2).strip()
            location = re.split(r"\.\s*(?:Meet|Roll|Leave)\b", location, maxsplit=1)[0].strip()
            return _normalize_meet_location(location)
    for line in text_lines:
        if "summit" in line.lower() and "palo" in line.lower():
            starting_match = _STARTING_AT_PATTERN.search(line)
            if starting_match:
                location = starting_match.group(1).strip()
                if " from " in location.lower():
                    location = re.split(r"(?i)\s+from\s+", location, maxsplit=1)[1].strip()
                return _normalize_meet_location(location)
            return _normalize_meet_location(line.strip().lstrip(": ").strip())
    for line in text_lines:
        if "summit" in line.lower() and "gatos" in line.lower():
            return _normalize_meet_location(line.strip().lstrip(": ").strip())
    return ""


def _infer_gps_from_location(text_lines: List[str]) -> str:
    for line in text_lines:
        lower_line = line.lower()
        for key, coords in KNOWN_LOCATIONS.items():
            if key in lower_line:
                return coords
    return ""


def _extract_gps_from_text(text: str) -> str:
    match = _GPS_PATTERN.search(text)
    if match:
        lat, lon = match.group(1), match.group(2)
        return f"{lat}, {lon}"
    return ""


def _clean_url(url: str) -> str:
    return url.strip().rstrip(",.)]>}\"'")


def _iter_route_candidates(soup: BeautifulSoup, text_lines: List[str]) -> List[str]:
    candidates: List[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = _clean_url(urljoin(ALTOVELO_EVENTS_URL, anchor["href"]))
        if _route_priority(href) >= 100 or href in seen:
            continue
        seen.add(href)
        candidates.append(href)

    for line in text_lines:
        for match in _URL_PATTERN.finditer(line):
            candidate = _clean_url(match.group(0))
            if _route_priority(candidate) >= 100 or candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)

    return candidates


def _route_priority(url: str) -> int:
    if _RIDEWITHGPS_ROUTE_PATTERN.match(url):
        return 0
    if _GARMIN_ROUTE_PATTERN.match(url):
        return 1
    if _STRAVA_ROUTE_PATTERN.match(url):
        return 2
    if _STRAVA_SEGMENT_PATTERN.match(url):
        return 3
    return 100


def _extract_route_url(soup: BeautifulSoup, text_lines: List[str]) -> str:
    candidates = _iter_route_candidates(soup, text_lines)
    if not candidates:
        return ""
    return min(candidates, key=lambda candidate: (_route_priority(candidate), candidates.index(candidate)))


def _convert_distance_to_meters(value: str, unit: str) -> float:
    numeric_value = _parse_compact_number(value)
    lowered_unit = unit.lower()
    if lowered_unit.startswith("km") or "kilometer" in lowered_unit:
        return numeric_value * 1000
    return numeric_value * 1609.34


def _convert_elevation_to_meters(value: str, unit: str) -> float:
    numeric_value = _parse_compact_number(value)
    lowered_unit = unit.lower()
    if lowered_unit.startswith("f"):
        return numeric_value * 0.3048
    return numeric_value


def _parse_compact_number(value: str) -> float:
    cleaned = value.strip().lower().replace(",", "")
    multiplier = 1000.0 if cleaned.endswith("k") else 1.0
    if cleaned.endswith("k"):
        cleaned = cleaned[:-1]
    return float(cleaned) * multiplier


def _extract_route_metrics(text_lines: List[str]) -> Dict[str, float]:
    search_lines = list(text_lines)
    search_lines.extend(
        f"{text_lines[index]} {text_lines[index + 1]}"
        for index in range(len(text_lines) - 1)
    )

    for line in search_lines:
        match = _ROUTE_METRICS_PATTERN.search(line)
        if not match:
            continue
        return {
            "distance_meters": _convert_distance_to_meters(
                match.group("distance"),
                match.group("distance_unit"),
            ),
            "elevation_gain_meters": _convert_elevation_to_meters(
                match.group("elevation"),
                match.group("elevation_unit"),
            ),
        }

    return {"distance_meters": 0.0, "elevation_gain_meters": 0.0}


def _extract_organizer(text_lines: List[str]) -> str:
    labeled_leader = _extract_labeled_value(text_lines, ("ride leader",), max_parts=1)
    if labeled_leader:
        return labeled_leader.lstrip(": ").strip()

    for index, line in enumerate(text_lines):
        match = _RIDE_LEADER_PATTERN.search(line)
        if match:
            organizer = match.group(1).strip()
            if organizer:
                return organizer
            if index + 1 < len(text_lines):
                next_line = text_lines[index + 1].strip()
                if next_line and ":" not in next_line:
                    return next_line
    return ""


def _extract_labeled_value(
    text_lines: List[str],
    labels: tuple[str, ...],
    *,
    max_parts: int = 3,
) -> str:
    lowered_labels = {label.lower() for label in labels}

    for index, line in enumerate(text_lines):
        stripped_line = line.strip()
        lowered_line = stripped_line.lower().rstrip(":")
        matched_label = next(
            (label for label in lowered_labels if lowered_line == label),
            None,
        )

        if matched_label is None:
            for label in lowered_labels:
                prefix = f"{label}:"
                if stripped_line.lower().startswith(prefix):
                    inline_value = stripped_line[len(prefix):].strip()
                    return _collect_continuation_value(
                        text_lines,
                        index,
                        inline_value=inline_value,
                        max_parts=max_parts,
                    )
            continue

        collected_value = _collect_continuation_value(
            text_lines,
            index,
            inline_value="",
            max_parts=max_parts,
        )
        if collected_value:
            return collected_value

    return ""


def _collect_continuation_value(
    text_lines: List[str],
    label_index: int,
    *,
    inline_value: str,
    max_parts: int,
) -> str:
    parts: List[str] = []
    if inline_value:
        parts.append(inline_value)

    lookahead = label_index + 1

    while lookahead < len(text_lines):
        candidate = text_lines[lookahead].strip()
        if _is_label_line(candidate) and candidate != ":":
            break
        if candidate.startswith("http"):
            break
        if candidate == "Alto Velo":
            break
        if not candidate:
            break

        if candidate == ":":
            lookahead += 1
            continue

        parts.append(candidate.lstrip(": ").strip())
        if candidate.endswith(".") and "meet" in candidate.lower():
            break
        if len(parts) >= max_parts:
            break
        lookahead += 1

    return " ".join(part for part in parts if part).strip()


def _is_label_line(candidate: str) -> bool:
    lowered_candidate = candidate.lower().strip()
    bare_candidate = lowered_candidate.rstrip(":")
    if bare_candidate in _LABEL_TERMINATORS:
        return True
    for label in _LABEL_TERMINATORS:
        if lowered_candidate.startswith(f"{label}:"):
            return True
    return False


def extract_event_detail(html: str) -> Dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    text_content = _extract_text_content(soup)
    text_lines = [line.strip() for line in text_content.split("\n") if line.strip()]
    route_metrics = _extract_route_metrics(text_lines)

    gps_coordinates = _extract_gps_from_text(text_content)
    if not gps_coordinates:
        gps_coordinates = _infer_gps_from_location(text_lines)

    return {
        "start_time": _extract_start_time(text_lines, text_content),
        "meet_up_location": _extract_location(text_lines),
        "route_url": _extract_route_url(soup, text_lines),
        "description": "\n".join(text_lines[:40]),
        "gps_coordinates": gps_coordinates,
        "distance_meters": route_metrics["distance_meters"],
        "elevation_gain_meters": route_metrics["elevation_gain_meters"],
        "organizer": _extract_organizer(text_lines),
    }


def _parse_start_time_to_time(value: str) -> datetime.time:
    if not value:
        return datetime.strptime("09:00 AM", "%I:%M %p").time()
    match = _TIME_PATTERN.search(value)
    if not match:
        return datetime.strptime("09:00 AM", "%I:%M %p").time()
    time_part = match.group(1).replace(".", ":")
    if ":" not in time_part:
        time_part = f"{time_part}:00"
    ampm = match.group(2).upper()
    ampm = ampm.replace(".", "")
    try:
        return datetime.strptime(f"{time_part} {ampm}", "%I:%M %p").time()
    except ValueError:
        return datetime.strptime("09:00 AM", "%I:%M %p").time()


def _determine_gps(location: str, provided: str) -> str:
    if provided:
        return provided
    if not location:
        return DEFAULT_MEET_GPS
    lower_loc = location.lower()
    for key, coords in KNOWN_LOCATIONS.items():
        if key in lower_loc:
            return coords
    return DEFAULT_MEET_GPS


def _normalize_meet_location(location: str) -> str:
    cleaned = location.strip().lstrip(": ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    normalized_key = re.sub(r"[^\w\s,]", "", cleaned.lower())
    normalized_key = re.sub(r"\s+", " ", normalized_key).strip()
    return CANONICAL_LOCATION_ALIASES.get(normalized_key, cleaned)


def _format_event_time(event_date: str, start_time: str) -> Optional[Dict[str, str]]:
    try:
        date_obj = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None
    time_obj = _parse_start_time_to_time(start_time)
    local_dt = PACIFIC_TZ.localize(datetime.combine(date_obj, time_obj))
    utc_dt = local_dt.astimezone(pytz.utc)
    return {"$date": utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}


def _generate_event_id(event_date: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    return f"webpage-{event_date}-{suffix}"


def _safe_metric(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_route_details(route_url: str) -> Dict[str, object]:
    if not route_url:
        return {}
    if "ridewithgps.com/routes/" in route_url:
        return extract_route_from_ridewithgps(route_url)
    if "connect.garmin.com" in route_url and "/course/" in route_url:
        return extract_route_from_garmin(route_url)
    if "strava.com/" in route_url:
        return extract_route_from_strava(route_url)
    return {}


def build_event_record(event_summary: Dict[str, str], detail: Dict[str, object]) -> Dict[str, object]:
    event_date = event_summary.get("event_date", "")
    start_time = detail.get("start_time", "")
    event_time = _format_event_time(event_date, start_time)
    meet_location = detail.get("meet_up_location") or DEFAULT_MEET_LOCATION
    gps_coordinates = _determine_gps(meet_location, detail.get("gps_coordinates", ""))
    distance_meters = _safe_metric(detail.get("distance_meters"))
    elevation_gain_meters = _safe_metric(detail.get("elevation_gain_meters"))
    route_url = detail.get("route_url", "")
    route_map_url = ""
    route_polyline = ""

    if route_url:
        try:
            route_info = _extract_route_details(route_url)
        except Exception as exc:
            print(f"  - Failed to extract route data for {route_url}: {exc}")
            route_info = {}

        provider_distance = _safe_metric(route_info.get("distance_meters"))
        provider_elevation = _safe_metric(route_info.get("elevation_gain_meters"))
        if provider_distance > 0:
            distance_meters = provider_distance
        if provider_elevation > 0:
            elevation_gain_meters = provider_elevation
        route_map_url = str(route_info.get("route_map_url", "") or "")
        route_polyline = str(route_info.get("route_polyline", "") or "")

    record: Dict[str, object] = {
        "_id": _generate_event_id(event_date or datetime.now(PACIFIC_TZ).strftime("%Y-%m-%d")),
        "source_type": "webpage",
        "source_group_id": {"$numberLong": "0"},
        "source_group_name": "altovelo-a-ride",
        "event_time_utc": event_time,
        "meet_up_location": meet_location,
        "gps_coordinates": gps_coordinates,
        "distance_meters": distance_meters,
        "elevation_gain_meters": elevation_gain_meters,
        "organizer": detail.get("organizer", ""),
        "title": event_summary.get("event_name", "Alto Velo Ride"),
        "description": detail.get("description", ""),
        "route_url": route_url,
        "route_map_url": route_map_url,
        "route_polyline": route_polyline,
        "is_active": True,
        "event_picture_urls": [],
        "source_url": event_summary.get("event_url", ""),
    }
    return record


def _event_merge_key(event: Dict[str, object]) -> str:
    source_url = str(event.get("source_url", "") or "").strip()
    if source_url:
        return f"source:{source_url}"
    return f"id:{event.get('_id', '')}"


def _event_sort_key(event: Dict[str, object]) -> datetime:
    event_time = event.get("event_time_utc")
    if isinstance(event_time, datetime):
        return event_time
    return datetime.max


def _merge_webpage_events(
    existing_events: List[Dict[str, object]],
    webpage_events: List[Dict[str, object]],
) -> tuple[List[Dict[str, object]], int, int]:
    merged_events = list(existing_events)
    index_by_key = {_event_merge_key(event): index for index, event in enumerate(merged_events)}
    added_count = 0
    updated_count = 0

    for raw_event in webpage_events:
        runtime_event = normalize_event_for_runtime(raw_event)
        if runtime_event is None:
            continue

        key = _event_merge_key(runtime_event)
        existing_index = index_by_key.get(key)
        if existing_index is not None:
            existing_event = merged_events[existing_index]
            runtime_event["_id"] = existing_event.get("_id", runtime_event.get("_id", ""))
            merged_events[existing_index] = runtime_event
            updated_count += 1
            continue

        merged_events.append(runtime_event)
        index_by_key[key] = len(merged_events) - 1
        added_count += 1

    merged_events.sort(key=_event_sort_key)
    return merged_events, added_count, updated_count


def _refresh_local_events_bundle(events_path: Path = DEFAULT_EVENTS_FILE) -> None:
    with events_path.open("r", encoding="utf-8") as infile:
        data = json.load(infile)

    js_content = f"window.LOCAL_EVENTS_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};"
    EVENTS_JS_PATH.write_text(js_content, encoding="utf-8")


def main() -> None:
    path = download_altovelo_webpage()
    print(f"Saved Alto Velo events page HTML to {path}")

    html = load_saved_webpage(path)
    events = extract_recent_events_from_html(html)

    print("Recent Alto Velo events (within last 2 weeks):")
    detailed_events: List[Dict[str, object]] = []
    for event in events:
        event_url = event.get("event_url", "")
        if not event_url:
            continue
        try:
            event_html = fetch_event_detail_html(event_url)
        except requests.RequestException as exc:
            print(f"  - Failed to download {event_url}: {exc}")
            continue
        details = extract_event_detail(event_html)
        record = build_event_record(event, details)
        detailed_events.append(record)
        print(json.dumps(record, ensure_ascii=False))

    if not detailed_events:
        print("No recent Alto Velo webpage events were extracted.")
        return

    existing_events = load_events_for_runtime(DEFAULT_EVENTS_FILE)
    merged_events, added_count, updated_count = _merge_webpage_events(
        existing_events,
        detailed_events,
    )
    save_events_to_storage(merged_events, DEFAULT_EVENTS_FILE)
    _refresh_local_events_bundle(DEFAULT_EVENTS_FILE)
    print(
        "Saved Alto Velo webpage events directly to "
        f"{DEFAULT_EVENTS_FILE} ({added_count} added, {updated_count} updated)"
    )
    print(f"Refreshed local events bundle at {EVENTS_JS_PATH}")


if __name__ == "__main__":
    main()
