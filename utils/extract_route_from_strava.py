"""Helpers for extracting route data from Strava route and segment pages."""

from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv()


_DEFAULT_HEADERS = {
    "User-Agent": os.getenv(
        "STRAVA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_POLYLINE_PATTERNS = [
    re.compile(r'"summary_polyline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'),
    re.compile(r'"polyline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'),
]
_DISTANCE_PATTERNS = [
    re.compile(r'"distance"\s*:\s*([0-9]+(?:\.[0-9]+)?)'),
]
_ELEV_GAIN_PATTERNS = [
    re.compile(r'"elevation_gain"\s*:\s*([0-9]+(?:\.[0-9]+)?)'),
    re.compile(r'"elevationGain"\s*:\s*([0-9]+(?:\.[0-9]+)?)'),
    re.compile(r'"elev_gain"\s*:\s*([0-9]+(?:\.[0-9]+)?)'),
]
_SEGMENT_ID_PATTERN = re.compile(r"/segments/(\d+)")
_ROUTE_ID_PATTERN = re.compile(r"/routes/(\d+)")

_CACHED_ACCESS_TOKEN: Optional[str] = None


class StravaRouteExtractionError(RuntimeError):
    """Raised when Strava route extraction fails."""


def extract_route_from_strava(url: str, *, access_token: Optional[str] = None) -> Dict[str, object]:
    """Return normalized route data for a Strava route or segment page."""

    if not url:
        raise ValueError("A Strava URL is required")

    token = _resolve_access_token(access_token)
    route_id = _parse_route_id(url)
    if route_id and token:
        try:
            return _fetch_route_via_api(route_id, token)
        except StravaRouteExtractionError:
            pass

    segment_id = _parse_segment_id(url)
    if segment_id and token:
        try:
            return _fetch_segment_via_api(segment_id, token, url)
        except StravaRouteExtractionError:
            pass

    return _fetch_via_html(url)


def _resolve_access_token(explicit_token: Optional[str]) -> Optional[str]:
    global _CACHED_ACCESS_TOKEN

    if explicit_token:
        return explicit_token

    env_token = os.getenv("STRAVA_ACCESS_TOKEN")
    if env_token:
        return env_token

    if _CACHED_ACCESS_TOKEN:
        return _CACHED_ACCESS_TOKEN

    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        return None

    try:
        response = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    token = payload.get("access_token")
    if isinstance(token, str) and token:
        _CACHED_ACCESS_TOKEN = token
        return token

    return None


def _fetch_route_via_api(route_id: str, token: str) -> Dict[str, object]:
    api_url = f"https://www.strava.com/api/v3/routes/{route_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(api_url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise StravaRouteExtractionError(
            f"Failed to fetch Strava route {route_id} via API"
        ) from exc

    if response.status_code == 401:
        refreshed_token = _refresh_access_token()
        if refreshed_token and refreshed_token != token:
            headers["Authorization"] = f"Bearer {refreshed_token}"
            try:
                response = requests.get(api_url, headers=headers, timeout=30)
            except requests.RequestException as exc:
                raise StravaRouteExtractionError(
                    f"Failed to fetch Strava route {route_id} via API"
                ) from exc

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise StravaRouteExtractionError(
            f"Failed to fetch Strava route {route_id} via API"
        ) from exc

    data = response.json()
    distance = data.get("distance")
    elevation = data.get("elevation_gain")
    map_urls = data.get("map_urls") or {}
    map_info = data.get("map") or {}
    polyline = map_info.get("summary_polyline") or map_info.get("polyline") or ""

    return {
        "distance_meters": int(round(distance)) if distance is not None else 0,
        "elevation_gain_meters": int(round(elevation)) if elevation is not None else 0,
        "route_map_url": map_urls.get("url", "") or "",
        "route_polyline": polyline,
    }


def _fetch_segment_via_api(segment_id: str, token: str, url: str) -> Dict[str, object]:
    api_url = f"https://www.strava.com/api/v3/segments/{segment_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(api_url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise StravaRouteExtractionError(
            f"Failed to fetch Strava segment {segment_id} via API"
        ) from exc

    if response.status_code == 401:
        refreshed_token = _refresh_access_token()
        if refreshed_token and refreshed_token != token:
            headers["Authorization"] = f"Bearer {refreshed_token}"
            try:
                response = requests.get(api_url, headers=headers, timeout=30)
            except requests.RequestException as exc:
                raise StravaRouteExtractionError(
                    f"Failed to fetch Strava segment {segment_id} via API"
                ) from exc

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise StravaRouteExtractionError(
            f"Failed to fetch Strava segment {segment_id} via API"
        ) from exc

    data = response.json()
    distance = data.get("distance")
    elevation = data.get("total_elevation_gain")
    if elevation is None:
        high = data.get("elevation_high")
        low = data.get("elevation_low")
        if high is not None and low is not None:
            elevation = max(high - low, 0)
    map_info = data.get("map") or {}
    polyline = map_info.get("polyline") or map_info.get("polyline_encoded") or ""

    return {
        "distance_meters": int(round(distance)) if distance is not None else 0,
        "elevation_gain_meters": int(round(elevation)) if elevation is not None else 0,
        "route_map_url": _extract_og_image(url) or "",
        "route_polyline": polyline,
    }


def _fetch_via_html(url: str) -> Dict[str, object]:
    html = _fetch_html(url)
    polyline = _extract_polyline(html)
    distance = _extract_first_float(_DISTANCE_PATTERNS, html)
    elevation = _extract_first_float(_ELEV_GAIN_PATTERNS, html)

    return {
        "distance_meters": distance if distance is not None else 0,
        "elevation_gain_meters": elevation if elevation is not None else 0,
        "route_map_url": _extract_og_image_from_html(html) or "",
        "route_polyline": polyline or "",
    }


def _refresh_access_token() -> Optional[str]:
    global _CACHED_ACCESS_TOKEN

    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        return None

    try:
        response = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    token = payload.get("access_token")
    if isinstance(token, str) and token:
        _CACHED_ACCESS_TOKEN = token
        return token

    return None


def _fetch_html(url: str) -> str:
    try:
        response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise StravaRouteExtractionError(f"Failed to download Strava page: {url}") from exc
    return response.text


def _parse_segment_id(url: str) -> Optional[str]:
    match = _SEGMENT_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _parse_route_id(url: str) -> Optional[str]:
    match = _ROUTE_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _extract_polyline(html: str) -> str:
    for pattern in _POLYLINE_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        raw = match.group(1)
        try:
            return json.loads(f'"{raw}"')
        except json.JSONDecodeError:
            return raw.replace("\\/", "/")
    return ""


def _extract_first_float(patterns: list[re.Pattern[str]], html: str) -> Optional[int]:
    for pattern in patterns:
        match = pattern.search(html)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        return int(round(value))
    return None


def _extract_og_image(url: str) -> Optional[str]:
    try:
        html = _fetch_html(url)
    except StravaRouteExtractionError:
        return None
    return _extract_og_image_from_html(html)


def _extract_og_image_from_html(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", property="og:image")
    return meta["content"].strip() if meta and meta.get("content") else None
