from __future__ import annotations

"""Utility to convert stored ride events into a dehydrated JSON format.

The dehydrated output keeps only the fields that are needed for manual
insertion into MongoDB (Extended JSON with $numberLong/$date wrappers).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "storage" / "events.json"
DEFAULT_OUTPUT = BASE_DIR / "storage" / "events_dehydrated.json"


def wrap_number_long(value: Any) -> Dict[str, str] | None:
    """Return a Mongo Extended JSON $numberLong wrapper when possible."""
    if value is None:
        return None
    if isinstance(value, dict) and "$numberLong" in value:
        return value
    return {"$numberLong": str(value)}


def isoformat_datetime(value: datetime) -> str:
    """Return an ISO 8601 string with milliseconds when available."""
    iso_value = value.isoformat()
    # Ensure we always include milliseconds so output matches existing docs.
    if value.microsecond == 0 and "." not in iso_value:
        if iso_value.endswith("Z"):
            return f"{iso_value[:-1]}.000Z"
        for tz_sep in ("+", "-"):
            idx = iso_value.rfind(tz_sep)
            if idx > 10:  # timezone information detected
                base = iso_value[:idx]
                suffix = iso_value[idx + 1 :]
                return f"{base}.000{tz_sep}{suffix}"
        return f"{iso_value}.000"
    return iso_value


def wrap_date(value: Any) -> Dict[str, str] | None:
    """Return a Mongo Extended JSON $date wrapper when possible."""
    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        return value
    if isinstance(value, datetime):
        iso_value = isoformat_datetime(value)
    else:
        iso_value = str(value)
    return {"$date": iso_value}


def ensure_list_of_strings(value: Any) -> List[str]:
    """Normalise picture URL fields into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def clean_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None entries recursively for a cleaner payload."""
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested = clean_dict(value)
            if nested:
                cleaned[key] = nested
            continue
        if isinstance(value, list):
            cleaned_list = [item for item in value if item not in (None, "")]
            cleaned[key] = cleaned_list
            continue
        cleaned[key] = value
    return cleaned


def dehydrate_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a hydrated event document into a dehydrated JSON object."""
    dehydrated = {k: v for k, v in event.items() if k != "raw_event"}

    dehydrated["source_event_id"] = wrap_number_long(dehydrated.get("source_event_id"))
    dehydrated["source_group_id"] = wrap_number_long(dehydrated.get("source_group_id"))
    dehydrated["event_time_utc"] = wrap_date(dehydrated.get("event_time_utc"))

    if "event_picture_urls" in dehydrated:
        dehydrated["event_picture_urls"] = ensure_list_of_strings(dehydrated["event_picture_urls"])
    elif "event_picture_url" in dehydrated:
        dehydrated["event_picture_urls"] = ensure_list_of_strings(dehydrated["event_picture_url"])
        dehydrated.pop("event_picture_url", None)
    else:
        dehydrated["event_picture_urls"] = []

    if not dehydrated.get("source_url"):
        dehydrated["source_url"] = dehydrated.get("strava_url", "")

    return clean_dict(dehydrated)


def load_events(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as infile:
        return json.load(infile)


def save_events(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as outfile:
        json.dump(list(events), outfile, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dehydrate ride events JSON data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to hydrated events JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination path for dehydrated JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events = load_events(args.input)
    dehydrated_events = [dehydrate_event(event) for event in events]
    save_events(args.output, dehydrated_events)
    print(f"Dehydrated {len(dehydrated_events)} events to {args.output}")


if __name__ == "__main__":
    main()
