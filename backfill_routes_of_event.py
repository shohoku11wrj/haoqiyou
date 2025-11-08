from __future__ import annotations

"""Backfill missing route details for stored cycling events."""

import re
from pathlib import Path
from typing import Dict

from utils.event_storage import (
    DEFAULT_EVENTS_FILE,
    load_events_for_runtime,
    save_events_to_storage,
)
from utils.extract_route_from_ridewithgps import extract_route_from_ridewithgps
from utils.route_utils import classify_route_loop

_RIDEWITHGPS_PATTERN = re.compile(r"https://ridewithgps\.com/routes/\S+")


def _extract_ridewithgps_url(event: Dict[str, object]) -> str:
    source_url = (event.get("source_url") or "").strip()
    if source_url.startswith("https://ridewithgps.com/routes/"):
        return source_url

    description = (event.get("description") or "").strip()
    if description:
        match = _RIDEWITHGPS_PATTERN.search(description)
        if match:
            candidate = match.group(0)
            return candidate.rstrip(",.)")

    return ""


def backfill_route_fields(events_path: Path | str = DEFAULT_EVENTS_FILE) -> None:
    path = Path(events_path)
    events = load_events_for_runtime(path)
    if not events:
        print(f"No events found in {path}")
        return

    # First pass: extract route details from Ride with GPS URLs
    updated = False
    attempted = 0
    successful = 0

    for event in events:
        route_url = _extract_ridewithgps_url(event)
        if not route_url:
            continue

        attempted += 1

        try:
            route = extract_route_from_ridewithgps(route_url)
        except Exception as exc:  # noqa: BLE001
            event_id = event.get("_id") or event.get("title") or route_url
            print(f"Failed to backfill route for {event_id}: {exc}")
            continue

        distance = route.get("distance_meters", 0) or 0
        elevation = route.get("elevation_gain_meters", 0) or 0
        map_url = route.get("route_map_url") or route.get("map_url") or ""
        polyline = route.get("route_polyline") or route.get("polyline") or ""

        changes_made = False
        if event.get("distance_meters") != distance:
            event["distance_meters"] = distance
            changes_made = True
        if event.get("elevation_gain_meters") != elevation:
            event["elevation_gain_meters"] = elevation
            changes_made = True
        if event.get("route_map_url") != map_url:
            event["route_map_url"] = map_url
            changes_made = True
        if event.get("route_polyline") != polyline:
            event["route_polyline"] = polyline
            changes_made = True
        if changes_made:
            updated = True
            successful += 1
    
    print(f"Backfilled {successful} of {attempted} Ride with GPS events and saved to {path}")

    # Second pass: classify route orientation for closed-loop routes
    updated = False
    attempted = 0
    successful = 0
    for event in events:
        polyline = event.get("route_polyline") or event.get("polyline") or ""
        orientation = event.get("route_orientation")
        attempted += 1
        if not orientation and polyline:
            _, direction = classify_route_loop(polyline)
            if direction:
                orientation = direction.value
                successful += 1
        if orientation and event.get("route_orientation") != orientation:
            event["route_orientation"] = orientation
            changes_made = True
    print(f"Backfilled {successful} of {attempted} Ride with GPS events and saved to {path}")

    if not updated:
        print("No events required backfilling.")
        return

    save_events_to_storage(events, path)


if __name__ == "__main__":
    backfill_route_fields()
