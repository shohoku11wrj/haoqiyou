"""Convert GPX geometry into an encoded polyline string.

The helper focuses on the single `storage/COURSE_1.gpx` track that ships with the
repository, but it also works with arbitrary GPX files when invoked from the
command line. Use ``python serialize_gpx.py --help`` to see the available
options.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, Sequence, Tuple
import xml.etree.ElementTree as ET

# Garmin exports use the GPX 1.1 namespace.
GPX_NAMESPACE = {"gpx": "http://www.topografix.com/GPX/1/1"}


def iter_gpx_points(gpx_path: Path) -> Iterator[Tuple[float, float]]:
    """Yield latitude/longitude pairs from GPX tracks or routes.

    Track points (``<trkpt>``) take precedence. When a file does not contain a
    track the function falls back to route points (``<rtept>``).
    """

    try:
        root = ET.parse(gpx_path).getroot()
    except ET.ParseError as exc:  # pragma: no cover - defensive guardrail
        raise ValueError(f"Unable to parse GPX file: {gpx_path}") from exc

    points = list(_iter_points(root, "trkpt"))
    if not points:
        points = list(_iter_points(root, "rtept"))
    if not points:
        raise ValueError(f"No track or route points found in {gpx_path}")

    yield from points


def _iter_points(root: ET.Element, tag: str) -> Iterator[Tuple[float, float]]:
    xpath = f".//gpx:{tag}"
    for element in root.findall(xpath, GPX_NAMESPACE):
        lat_text = element.get("lat")
        lon_text = element.get("lon")
        if lat_text is None or lon_text is None:
            continue
        try:
            yield float(lat_text), float(lon_text)
        except ValueError:
            continue


def encode_polyline(points: Iterable[Sequence[float]], precision: int = 5) -> str:
    """Encode an iterable of latitude/longitude pairs as a Google polyline."""

    if precision < 0:
        raise ValueError("Precision must be a non-negative integer")

    factor = 10**precision
    encoded_chunks: list[str] = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in points:
        lat_i = int(round(lat * factor))
        lng_i = int(round(lng * factor))
        encoded_chunks.append(_encode_number(lat_i - prev_lat))
        encoded_chunks.append(_encode_number(lng_i - prev_lng))
        prev_lat = lat_i
        prev_lng = lng_i

    return "".join(encoded_chunks)


def _encode_number(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunk_chars: list[str] = []
    while value >= 0x20:
        chunk_chars.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunk_chars.append(chr(value + 63))
    return "".join(chunk_chars)


def build_payload(gpx_path: Path, precision: int) -> dict[str, object]:
    points = list(iter_gpx_points(gpx_path))
    encoded = encode_polyline(points, precision=precision)
    return {
        "source": str(gpx_path),
        "point_count": len(points),
        "precision": precision,
        "route_polyline": encoded,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serialize a GPX file into an encoded polyline")
    parser.add_argument(
        "gpx",
        nargs="?",
        default="storage/COURSE_1.gpx",
        help="Path to the GPX file (default: storage/COURSE_1.gpx)",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=5,
        help="Decimal precision used for encoding (default: 5)",
    )
    parser.add_argument(
        "--write-json",
        type=Path,
        help="Optional path to save the encoded output as JSON",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent level when writing JSON output (default: 2)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gpx_path = Path(args.gpx).expanduser()
    if not gpx_path.exists():
        raise FileNotFoundError(f"GPX file not found: {gpx_path}")

    payload = build_payload(gpx_path, precision=args.precision)

    if args.write_json:
        json_path = args.write_json.expanduser()
        json_text = json.dumps(payload, indent=args.indent, ensure_ascii=False)
        json_path.write_text(json_text, encoding="utf-8")
        print(f"Wrote encoded route with {payload['point_count']} points to {json_path}")
    else:
        # python serialize_gpx.py --write-json storage/course1.json
        print(payload["route_polyline"])


if __name__ == "__main__":
    main()
