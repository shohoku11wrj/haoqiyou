#!/usr/bin/env python3
"""Utility script for pruning stale Strava events from storage/events.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EVENTS_PATH = BASE_DIR / "storage" / "events.json"

# Groups that regularly sync from Strava whose older events should be removed.
STRAVA_GROUP_IDS = {265, 1047313, 1115522, 908336}


def parse_number_long(value: Any) -> Optional[int]:
    """Return the numeric value stored in Mongo Extended JSON containers."""

    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("$numberLong", "$numberInt"):
            if key in value:
                value = value[key]
                break
        else:
            return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_event_datetime(value: Any) -> Optional[datetime]:
    """Extract a timezone-aware datetime from extended JSON formats."""

    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        value = value["$date"]
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str):
        value = str(value)

    iso_value = value.strip()
    if not iso_value:
        return None
    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def should_remove_event(event: Dict[str, Any], cutoff: datetime) -> bool:
    if event.get("source_type") != "strava":
        return False
    group_id = parse_number_long(event.get("source_group_id"))
    if group_id not in STRAVA_GROUP_IDS:
        return False
    event_time = parse_event_datetime(event.get("event_time_utc"))
    if event_time is None:
        return False
    return event_time < cutoff


def cleanup_events(events: Iterable[Dict[str, Any]], cutoff: datetime) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    for event in events:
        if should_remove_event(event, cutoff):
            removed.append(event)
        else:
            kept.append(event)
    return kept, removed


def load_events(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def save_events(path: Path, events: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        json.dump(events, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def format_event_summary(event: Dict[str, Any]) -> str:
    group_id = parse_number_long(event.get("source_group_id"))
    event_time = parse_event_datetime(event.get("event_time_utc"))
    return f"{event.get('_id', 'unknown')} (group {group_id}, event_time={event_time})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up Strava events older than one month.")
    parser.add_argument(
        "--events-file",
        type=Path,
        default=DEFAULT_EVENTS_PATH,
        help="Path to storage/events.json (defaults to project storage).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the events that would be removed without modifying the file.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=8,
        help="Age threshold in days (default: 8).",
    )
    args = parser.parse_args()

    events_file: Path = args.events_file
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    events = load_events(events_file)
    kept, removed = cleanup_events(events, cutoff)

    print(f"Loaded {len(events)} events.")
    print(f"Cutoff datetime (UTC): {cutoff.isoformat()}")
    print(f"Identified {len(removed)} stale Strava events for removal.")

    if args.dry_run:
        for event in removed:
            print("DRY-RUN", format_event_summary(event))
        print("Dry run complete; no changes were written.")
        return

    save_events(events_file, kept)
    print(f"Saved {len(kept)} remaining events to {events_file}.")


if __name__ == "__main__":
    main()
