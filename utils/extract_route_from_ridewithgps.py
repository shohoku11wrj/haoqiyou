"""Helpers for extracting route data from Ride with GPS pages."""

from __future__ import annotations

import os
from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


_JSON_HEADERS = {
    "User-Agent": os.getenv(
        "RIDEWITHGPS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ),
    "Accept": "application/json, text/plain, */*",
}

_HTML_HEADERS = {
    "User-Agent": _JSON_HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_route_from_ridewithgps(url: str) -> Dict[str, Any]:
    """Return normalized route fields for a Ride with GPS route page.

    Args:
        url: Public Ride with GPS route URL.

    Returns:
        A dictionary with distance/elevation (meters), a map image URL and an
        encoded Google polyline string.
    """

    if not url:
        raise ValueError("A Ride with GPS route URL is required")

    json_url = _build_json_url(url)
    payload = _fetch_route_payload(json_url)

    distance = _safe_float(payload.get("distance"))
    elevation = _safe_float(payload.get("elevation_gain"))

    coordinates = _extract_coordinates(payload)
    polyline = _encode_polyline(coordinates) if coordinates else ""

    map_url = _extract_map_image(url)

    return {
        "distance_meters": int(round(distance)) if distance is not None else 0,
        "elevation_gain_meters": int(round(elevation)) if elevation is not None else 0,
        "route_map_url": map_url or "",
        "route_polyline": polyline,
    }


def _build_json_url(route_url: str) -> str:
    parsed = urlparse(route_url)

    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "ridewithgps.com"
    path = parsed.path.rstrip("/")

    if not path:
        raise ValueError(f"Invalid Ride with GPS route URL: {route_url}")

    if not path.endswith(".json"):
        path = f"{path}.json"

    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _fetch_route_payload(json_url: str) -> Dict[str, Any]:
    try:
        response = requests.get(json_url, headers=_JSON_HEADERS, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Ride with GPS route data from {json_url}") from exc

    if response.status_code in {403, 404} or "json" not in response.headers.get("Content-Type", "").lower():
        alt_url = _ensure_query_parameter(json_url, "format", "json")
        if alt_url != json_url:
            try:
                response = requests.get(alt_url, headers=_JSON_HEADERS, timeout=30)
            except requests.RequestException as exc:
                raise RuntimeError(f"Failed to load Ride with GPS route data from {alt_url}") from exc
            json_url = alt_url

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to load Ride with GPS route data from {json_url}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("Ride with GPS route endpoint returned non-JSON data") from exc


def _ensure_query_parameter(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)

    updated = dict(query_pairs)
    if updated.get(key) == value:
        return url

    updated[key] = value
    new_query = urlencode(updated, doseq=True)

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def _extract_map_image(route_url: str) -> Optional[str]:
    try:
        response = requests.get(route_url, headers=_HTML_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    meta = soup.find("meta", property="og:image")
    return meta["content"].strip() if meta and meta.get("content") else None


def _extract_coordinates(payload: Any) -> List[Tuple[float, float]]:
    queue: deque[Any] = deque([payload])

    while queue:
        current = queue.popleft()

        if isinstance(current, dict):
            for key, value in current.items():
                lowered = key.lower()
                if lowered in {"track_points", "trackpoints", "points", "coordinates", "course_points"}:
                    coords = _coerce_coordinate_sequence(value)
                    if coords:
                        return coords
                elif lowered == "route_path" and isinstance(value, dict):
                    coords = _coerce_coordinate_sequence(value.get("coordinates"))
                    if coords:
                        return coords
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)

    return []


def _coerce_coordinate_sequence(data: Any) -> List[Tuple[float, float]]:
    if isinstance(data, dict):
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


def _encode_polyline(coordinates: Iterable[Iterable[float]], precision: int = 5) -> str:
    factor = 10 ** precision

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


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
