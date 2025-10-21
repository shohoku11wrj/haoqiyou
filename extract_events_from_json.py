from __future__ import annotations

"""Extract the encoded Ride with GPS route polyline from a stored JSON file."""

import json
from collections import deque
from pathlib import Path
from typing import Any, Deque, Iterable, List, Optional, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent


def extract_encoded_route(json_path: str | Path) -> str:
    """Return the encoded polyline string contained within the saved JSON file."""

    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Ride with GPS JSON not found at {path}")

    try:
        with path.open("r", encoding="utf-8") as infile:
            payload = json.load(infile)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load Ride with GPS data from {path}") from exc

    coordinates = _collect_coordinates(payload)
    if not coordinates:
        raise ValueError(f"Unable to locate route coordinates in {path}")

    return _encode_polyline(coordinates)


def _collect_coordinates(payload: Any) -> List[Tuple[float, float]]:
    """Traverse nested JSON looking for the densest latitude/longitude list."""

    queue: Deque[Any] = deque([payload])
    best: List[Tuple[float, float]] = []
    seen: set[int] = set()

    while queue:
        current = queue.popleft()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)

        coords = _coerce_coordinate_sequence(current)
        if coords and len(coords) > len(best):
            best = coords

        if isinstance(current, dict):
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)

    return best


def _coerce_coordinate_sequence(data: Any) -> List[Tuple[float, float]]:
    """Convert a sequence of points into (lat, lon) pairs when possible."""

    if isinstance(data, dict):
        nested = data.get("coordinates") if "coordinates" in data else None
        if nested is not None:
            return _coerce_coordinate_sequence(nested)
        nested = data.get("points") if "points" in data else None
        if nested is not None:
            return _coerce_coordinate_sequence(nested)
        nested = data.get("track_points") if "track_points" in data else None
        if nested is not None:
            return _coerce_coordinate_sequence(nested)
        return []

    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        return []

    coords: List[Tuple[float, float]] = []

    for entry in data:
        lat_lon: Optional[Tuple[float, float]] = None

        if isinstance(entry, dict):
            lat_lon = _latlon_from_dict(entry)
        elif isinstance(entry, Sequence) and not isinstance(entry, (str, bytes, bytearray)):
            if len(entry) >= 2:
                lat_lon = _latlon_from_sequence(entry)

        if not lat_lon:
            continue

        if coords and lat_lon == coords[-1]:
            continue

        coords.append(lat_lon)

    return coords


def _latlon_from_dict(entry: dict[str, Any]) -> Optional[Tuple[float, float]]:
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


def _latlon_from_sequence(entry: Sequence[Any]) -> Optional[Tuple[float, float]]:
    try:
        lat = float(entry[0])
        lon = float(entry[1])
    except (TypeError, ValueError, IndexError):
        return None
    return lat, lon


def _guess_lat_lon_keys(entry: dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    lat_key: Optional[str] = None
    lon_key: Optional[str] = None

    for key in entry.keys():
        lower = key.lower()
        if lower.startswith("lat") and lat_key is None:
            lat_key = key
        elif lower.startswith("lon") or lower.startswith("lng"):
            if lon_key is None:
                lon_key = key

    if lat_key and lon_key:
        return lat_key, lon_key

    numeric_keys = [key for key in entry.keys() if isinstance(key, str) and key.isdigit()]
    if len(numeric_keys) >= 2:
        numeric_keys.sort()
        return numeric_keys[0], numeric_keys[1]

    return None, None


def _encode_polyline(coordinates: Iterable[Iterable[float]], precision: int = 5) -> str:
    """Encode coordinates using Google's polyline algorithm."""

    factor = 10 ** precision
    encoded_chars: List[str] = []
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
    chunk_chars: List[str] = []
    while value >= 0x20:
        chunk_chars.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunk_chars.append(chr(value + 63))
    return "".join(chunk_chars)


def main() -> None:
    # Route info of RideWithGPS has been implemented in utils/fetch_ridewithgps.py
    encoded = extract_encoded_route("storage/ridewithgps.json")
    print(json.dumps(encoded))
    # Route polyline of FootPathApp can be fetched from HTTP response directly.


if __name__ == "__main__":
    main()
