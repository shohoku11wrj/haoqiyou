"""Helpers for working with encoded route polylines."""

from __future__ import annotations

import base64
import binascii
import math
from typing import Iterable, List, Sequence, Tuple

from utils.constants import RouteOrientation

BASE64_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r")
EARTH_RADIUS_M = 6_371_000.0
DEFAULT_PRECISION = 5
DEFAULT_CLOSURE_THRESHOLD_M = 50.0
AREA_EPSILON = 1e-12


def _maybe_decode_base64(encoded: str) -> str:
    """Return the decoded polyline when the input looks like base64 text."""

    if not encoded:
        return ""

    candidate = encoded.strip()
    if not candidate:
        return ""

    if not set(candidate) <= BASE64_CHARS:
        return candidate

    padded = candidate + "=" * (-len(candidate) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True)
        decoded_text = decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return candidate

    return decoded_text or ""


def _decode_value(polyline: str, index: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if index >= len(polyline):
            raise ValueError("Truncated polyline string")
        byte = ord(polyline[index]) - 63
        index += 1
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            break
    delta = ~(result >> 1) if (result & 1) else (result >> 1)
    return delta, index


def decode_polyline(polyline: str, precision: int = DEFAULT_PRECISION) -> List[Tuple[float, float]]:
    """Decode a Google-style polyline string into latitude/longitude pairs."""

    if precision < 0:
        raise ValueError("Precision must be non-negative")

    factor = 10 ** precision
    lat = 0
    lng = 0
    index = 0
    coords: List[Tuple[float, float]] = []

    while index < len(polyline):
        d_lat, index = _decode_value(polyline, index)
        d_lng, index = _decode_value(polyline, index)
        lat += d_lat
        lng += d_lng
        coords.append((lat / factor, lng / factor))

    return coords


def _haversine_distance_m(a: Sequence[float], b: Sequence[float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d_phi = lat2 - lat1
    d_lambda = lon2 - lon1
    sin_dphi = math.sin(d_phi / 2.0)
    sin_dlambda = math.sin(d_lambda / 2.0)
    value = sin_dphi**2 + math.cos(lat1) * math.cos(lat2) * sin_dlambda**2
    value = min(1.0, max(0.0, value))
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def _dedupe_sequential(points: Iterable[Sequence[float]]) -> List[Tuple[float, float]]:
    deduped: List[Tuple[float, float]] = []
    prev: Tuple[float, float] | None = None
    for lat, lon in points:
        current = (lat, lon)
        if prev is None or abs(current[0] - prev[0]) > 1e-7 or abs(current[1] - prev[1]) > 1e-7:
            deduped.append(current)
            prev = current
    return deduped


def _signed_area(points: Sequence[Sequence[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i in range(len(points)):
        lat1, lon1 = points[i]
        lat2, lon2 = points[(i + 1) % len(points)]
        area += lon1 * lat2 - lon2 * lat1
    return area / 2.0


def classify_route_loop(
    route_polyline: str,
    *,
    precision: int = DEFAULT_PRECISION,
    closure_threshold_m: float = DEFAULT_CLOSURE_THRESHOLD_M,
) -> Tuple[bool, RouteOrientation | None]:
    """Return (is_loop, orientation) for the supplied route polyline.

    The orientation value is ``RouteOrientation.CLOCKWISE`` or
    ``RouteOrientation.COUNTERCLOCKWISE`` when the
    geometry forms a closed loop. ``None`` indicates the shape is not a loop or
    the winding direction cannot be determined (e.g., degenerate area).
    """

    decoded_polyline = _maybe_decode_base64(route_polyline)
    if not decoded_polyline:
        return False, None

    try:
        points = decode_polyline(decoded_polyline, precision=precision)
    except ValueError:
        return False, None

    cleaned = _dedupe_sequential(points)
    if len(cleaned) < 3:
        return False, None

    if _haversine_distance_m(cleaned[0], cleaned[-1]) > closure_threshold_m:
        return False, None

    area = _signed_area(cleaned)
    if abs(area) <= AREA_EPSILON:
        return True, None

    orientation = (
        RouteOrientation.COUNTERCLOCKWISE if area > 0 else RouteOrientation.CLOCKWISE
    )
    return True, orientation
