from __future__ import annotations

"""Helpers for loading and saving event data without MongoDB dependencies."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pytz

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EVENTS_FILE = BASE_DIR / "storage" / "events.json"
UTC = pytz.utc


def unwrap_number_long(value: Any) -> Any:
    """Return the numeric value stored in a MongoDB $numberLong wrapper."""
    if isinstance(value, dict):
        raw_value = value.get("$numberLong") or value.get("$oid")
        if raw_value is not None:
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                return raw_value
    return value


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, dict):
        value = value.get("$date")
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        normalised = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalised)
        except ValueError:
            return None
    elif value is None:
        return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)


def normalize_event_for_runtime(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise a stored event for in-memory processing."""
    normalised = dict(event)
    if "source_group_id" in normalised:
        normalised["source_group_id"] = unwrap_number_long(normalised.get("source_group_id"))
    if "source_event_id" in normalised:
        normalised["source_event_id"] = unwrap_number_long(normalised.get("source_event_id"))

    event_time = _coerce_datetime(normalised.get("event_time_utc"))
    if event_time is None:
        return None
    normalised["event_time_utc"] = event_time

    if not normalised.get("_id"):
        normalised["_id"] = (
            f"{normalised.get('source_type', 'event')}"
            f"-{normalised.get('source_group_id', 'unknown')}"
            f"-{normalised.get('source_event_id', 'unknown')}"
        )

    return normalised


def load_events_for_runtime(
    path: Optional[Path] = None,
    *,
    active_only: bool = False,
) -> List[Dict[str, Any]]:
    """Load events from storage JSON into runtime-friendly dictionaries."""

    events_path = path or DEFAULT_EVENTS_FILE
    if not events_path.exists():
        return []

    try:
        with events_path.open("r", encoding="utf-8") as infile:
            stored_events = json.load(infile)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: unable to load events from {events_path}: {exc}")
        return []

    runtime_events: List[Dict[str, Any]] = []
    for stored_event in stored_events:
        normalised = normalize_event_for_runtime(stored_event)
        if not normalised:
            continue
        if active_only and not normalised.get("is_active", True):
            continue
        runtime_events.append(normalised)
    return runtime_events


def isoformat_datetime(value: datetime) -> str:
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    iso_value = dt.isoformat().replace("+00:00", "Z")
    if dt.microsecond == 0 and "." not in iso_value:
        iso_value = iso_value.replace("Z", ".000Z")
    return iso_value


def wrap_number_long(value: Any) -> Optional[Dict[str, str]]:
    if value is None:
        return None
    if isinstance(value, dict) and "$numberLong" in value:
        return value
    return {"$numberLong": str(value)}


def wrap_date(value: Any) -> Optional[Dict[str, str]]:
    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        return value
    dt = _coerce_datetime(value)
    if dt is None:
        return None
    return {"$date": isoformat_datetime(dt)}


def ensure_list_of_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def clean_dict(data: Dict[str, Any]) -> Dict[str, Any]:
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


def rehydrate_event_for_storage(event: Dict[str, Any]) -> Dict[str, Any]:
    hydrated = dict(event)

    if "source_event_id" in hydrated:
        hydrated["source_event_id"] = wrap_number_long(hydrated.get("source_event_id"))
    if "source_group_id" in hydrated:
        hydrated["source_group_id"] = wrap_number_long(hydrated.get("source_group_id"))

    if "event_time_utc" in hydrated:
        event_time = wrap_date(hydrated.get("event_time_utc"))
        if event_time is not None:
            hydrated["event_time_utc"] = event_time
        else:
            hydrated.pop("event_time_utc", None)

    if "event_picture_urls" in hydrated:
        hydrated["event_picture_urls"] = ensure_list_of_strings(hydrated["event_picture_urls"])
    elif "event_picture_url" in hydrated:
        hydrated["event_picture_urls"] = ensure_list_of_strings(hydrated["event_picture_url"])
        hydrated.pop("event_picture_url", None)
    else:
        hydrated["event_picture_urls"] = []

    if not hydrated.get("source_url"):
        hydrated["source_url"] = hydrated.get("strava_url", "")

    return clean_dict(hydrated)


def save_events_to_storage(
    events: Iterable[Dict[str, Any]],
    path: Optional[Path] = None,
) -> None:
    events_path = path or DEFAULT_EVENTS_FILE
    events_path.parent.mkdir(parents=True, exist_ok=True)
    serialised_events = [rehydrate_event_for_storage(event) for event in events]
    with events_path.open("w", encoding="utf-8") as outfile:
        json.dump(serialised_events, outfile, indent=2)
