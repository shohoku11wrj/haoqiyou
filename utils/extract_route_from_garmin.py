"""Helpers for extracting route data from Garmin Connect course pages."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


_DEFAULT_USER_AGENT = os.getenv(
    "GARMIN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
)

_HTML_HEADERS = {
    "User-Agent": _DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_JSON_HEADERS = {
    "User-Agent": _DEFAULT_USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://connect.garmin.com",
    "NK": "NT",
    "X-app-ver": os.getenv("GARMIN_URL_BUST", "5.17.3.2"),
    "X-lang": os.getenv("GARMIN_LOCALE", "en-US"),
}

_COURSE_ID_PATTERN = re.compile(r"/course/?(\d+)")
_DISTANCE_KEYS = {
    "distance",
    "distancemeters",
    "distanceinmeters",
    "totaldistance",
    "totaldistanceinmeters",
}
_ELEVATION_KEYS = {
    "elevationgain",
    "elevationgaininmeters",
    "totalelevationgain",
    "totalelevationgaininmeters",
    "ascent",
    "totalascent",
}


class GarminRouteExtractionError(RuntimeError):
    """Raised when Garmin route extraction fails."""


def extract_route_from_garmin(url: str) -> Dict[str, object]:
    """Return normalized route data for a Garmin Connect course page."""

    if not url:
        raise ValueError("A Garmin course URL is required")

    course_id = _parse_course_id(url)
    if not course_id:
        raise ValueError(f"Unable to parse Garmin course id from URL: {url}")

    session = requests.Session()
    _apply_cookie_overrides(session)

    try:
        session.get(url, headers=_HTML_HEADERS, timeout=30)
    except requests.RequestException:
        # Some public course endpoints still work even if the landing page fails.
        pass

    payload = _fetch_course_payload(session, course_id, url)
    polyline = _extract_polyline_from_payload(payload) or ""
    distance = _extract_metric(payload, _DISTANCE_KEYS) or 0.0
    elevation = _extract_metric(payload, _ELEVATION_KEYS) or 0.0
    map_url = _extract_map_image(session, url) or ""

    return {
        "distance_meters": int(round(distance)),
        "elevation_gain_meters": int(round(elevation)),
        "route_map_url": map_url,
        "route_polyline": polyline,
    }


def _parse_course_id(url: str) -> Optional[str]:
    match = _COURSE_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _fetch_course_payload(
    session: requests.Session,
    course_id: str,
    course_url: str,
) -> Any:
    api_url = f"https://connect.garmin.com/modern/proxy/course-service/course/{course_id}"
    headers = dict(_JSON_HEADERS)
    headers["Referer"] = course_url

    try:
        response = session.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GarminRouteExtractionError(
            f"Failed to load Garmin course data for {course_id}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise GarminRouteExtractionError("Garmin course API returned non-JSON data") from exc

    if not payload:
        raise GarminRouteExtractionError(
            "Garmin course API returned an empty payload. Authentication may be required."
        )

    return payload


def _extract_metric(payload: Any, accepted_keys: set[str]) -> Optional[float]:
    queue: deque[Any] = deque([payload])
    seen: set[int] = set()

    while queue:
        current = queue.popleft()

        if isinstance(current, (dict, list)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)

        if isinstance(current, dict):
            for key, value in current.items():
                normalised_key = _normalise_key(key)
                if normalised_key in accepted_keys:
                    numeric_value = _safe_float(value)
                    if numeric_value is not None and numeric_value > 0:
                        return numeric_value
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)

    return None


def _extract_polyline_from_payload(payload: Any) -> Optional[str]:
    queue: deque[Any] = deque([payload])
    seen: set[int] = set()

    while queue:
        current = queue.popleft()

        if isinstance(current, (dict, list)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)

        if isinstance(current, dict):
            for key, value in current.items():
                normalised_key = _normalise_key(key)
                if "polyline" in normalised_key and isinstance(value, str) and value:
                    return value
                if normalised_key == "polylinedto" and isinstance(value, list):
                    encoded = _encode_from_points(value)
                    if encoded:
                        return encoded
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)

    return None


def _extract_map_image(session: requests.Session, route_url: str) -> Optional[str]:
    try:
        response = session.get(route_url, headers=_HTML_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    meta = soup.find("meta", property="og:image")
    return meta["content"].strip() if meta and meta.get("content") else None


def _encode_from_points(points: Iterable[Any]) -> Optional[str]:
    coords: List[Tuple[float, float]] = []

    for point in points:
        if not isinstance(point, dict):
            continue

        lat = point.get("latitude")
        if lat is None:
            lat = point.get("lat")

        lon = point.get("longitude")
        if lon is None:
            lon = point.get("lon")

        try:
            if lat is None or lon is None:
                continue
            coords.append((float(lat), float(lon)))
        except (TypeError, ValueError):
            continue

    if not coords:
        return None

    return _encode_polyline(coords)


def _encode_polyline(coordinates: Iterable[Tuple[float, float]], precision: int = 5) -> str:
    factor = 10**precision
    output: List[str] = []
    prev_lat = 0
    prev_lon = 0

    for lat, lon in coordinates:
        lat_i = int(round(lat * factor))
        lon_i = int(round(lon * factor))

        output.append(_encode_polyline_value(lat_i - prev_lat))
        output.append(_encode_polyline_value(lon_i - prev_lon))

        prev_lat = lat_i
        prev_lon = lon_i

    return "".join(output)


def _encode_polyline_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunks: List[str] = []

    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5

    chunks.append(chr(value + 63))
    return "".join(chunks)


def _apply_cookie_overrides(session: requests.Session) -> None:
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


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
