from __future__ import annotations

import unittest
from pathlib import Path

from update_webpage_events import _determine_gps, extract_event_detail


BASE_DIR = Path(__file__).resolve().parent.parent
EVENT_PAGES_DIR = BASE_DIR / "storage" / "event_pages"


class UpdateWebpageEventsTest(unittest.TestCase):
    def test_prefers_route_url_over_segment_url(self) -> None:
        html = """
        <article>
          <p>LKHC segment is <a href="https://www.strava.com/segments/627955">Portola State Park</a></p>
          <p>Route: https://www.strava.com/routes/3424539058421593332</p>
          <p>Summary: 59 miles / 6800 feet</p>
          <p>Start/End: Summit Bicycles, Palo Alto</p>
          <p>Time: Meet 9 AM, roll out 9:10 AM</p>
          <p>Ride Leader: Kevin Kauffman</p>
        </article>
        """

        detail = extract_event_detail(html)

        self.assertEqual(
            detail["route_url"],
            "https://www.strava.com/routes/3424539058421593332",
        )
        self.assertEqual(detail["organizer"], "Kevin Kauffman")
        self.assertAlmostEqual(detail["distance_meters"], 94951.06, places=2)
        self.assertAlmostEqual(detail["elevation_gain_meters"], 2072.64, places=2)

    def test_prefers_meet_time_over_other_prose_times(self) -> None:
        html_path = EVENT_PAGES_DIR / "altovelo-av-a-ride-saturday-91325-cloverdale-to-av-picnic.html"
        detail = extract_event_detail(html_path.read_text(encoding="utf-8"))

        self.assertEqual(detail["start_time"], "9:00 AM")
        self.assertEqual(detail["meet_up_location"], "Summit Bicycles, Palo Alto")
        self.assertEqual(detail["organizer"], "Jack Lund")
        self.assertEqual(
            detail["route_url"],
            "https://www.strava.com/routes/3401322226272041182",
        )

    def test_parses_compact_summary_metrics(self) -> None:
        html_path = EVENT_PAGES_DIR / "altovelo-saturday-a-ride-8am-choose-your-own-adventure.html"
        detail = extract_event_detail(html_path.read_text(encoding="utf-8"))

        self.assertEqual(detail["start_time"], "8am")
        self.assertEqual(detail["meet_up_location"], "Summit Bicycles, Palo Alto")
        self.assertEqual(detail["organizer"], "Wil Gibb")
        self.assertAlmostEqual(detail["distance_meters"], 109435.12, places=1)
        self.assertAlmostEqual(detail["elevation_gain_meters"], 1950.72, places=1)

    def test_parses_split_label_blocks(self) -> None:
        html = """
        <article>
          <p>Route</p>
          <p>:</p>
          <p>https://connect.garmin.com/app/course/447062393</p>
          <p>Summary</p>
          <p>: 111 miles / 6600 feet</p>
          <p>Start</p>
          <p>: Summit Bicycles, Palo Alto</p>
          <p>Time</p>
          <p>: NOTE EARLY START TIME! Meet 8 a.m., Leave 8:10 a.m.</p>
          <p>Ride Leader</p>
          <p>: Andrew Ernst</p>
        </article>
        """

        detail = extract_event_detail(html)

        self.assertEqual(detail["route_url"], "https://connect.garmin.com/app/course/447062393")
        self.assertEqual(detail["meet_up_location"], "Summit Bicycles, Palo Alto")
        self.assertEqual(detail["start_time"], "8 a.m.")
        self.assertEqual(detail["organizer"], "Andrew Ernst")
        self.assertAlmostEqual(detail["distance_meters"], 178636.74, places=1)
        self.assertAlmostEqual(detail["elevation_gain_meters"], 2011.68, places=1)

    def test_normalizes_known_summit_locations(self) -> None:
        palo_alto_html = """
        <article>
          <p>Ride stats</p>
          <p>: 77 mi and 3150 ft (123 km and 960 m) starting at 9:00 AM from Summit Bikes in Palo Alto</p>
          <p>Route: https://www.strava.com/routes/1</p>
        </article>
        """
        los_gatos_html = """
        <article>
          <p>Start: Summit Bicycles,</p>
          <p>Los Gatos</p>
          <p>. Meet 9:00 AM, Roll 9:10 AM</p>
        </article>
        """

        palo_alto_detail = extract_event_detail(palo_alto_html)
        los_gatos_detail = extract_event_detail(los_gatos_html)

        self.assertEqual(palo_alto_detail["meet_up_location"], "Summit Bicycles, Palo Alto")
        self.assertEqual(los_gatos_detail["meet_up_location"], "Summit Bicycles, Los Gatos")

    def test_infers_distinct_gps_for_known_summit_locations(self) -> None:
        self.assertEqual(
            _determine_gps("Summit Bicycles, Palo Alto", ""),
            "37.42797, -122.14508",
        )
        self.assertEqual(
            _determine_gps("Summit Bicycles, Los Gatos", ""),
            "37.2215127, -121.9787266",
        )


if __name__ == "__main__":
    unittest.main()
