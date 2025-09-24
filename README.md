# haoqiyou
HaoQiYou 好骑友 riding events whiteboard

## 2024-08-03 First Version
Production on https://haoqiyou.net
## 2024-08-20 Beta Version
Staging on https://haoqiyou.net/dev

 * Step 1. Execute `update_strata_events.py` to fetch ride events from Strava to MongoDB
 * Step 2. Execute `load_html_script.py` to generate HTML into file `index.html`

TODO:
 * [x] Event detail page & event detail path for each event
 * [x] Share one event via event detail path, or generate a postcard for one event to share
 * [x] Simplify the index page, reduce layout size of each event so that events can be organized compactly (卡片式，瀑布式); hide some details of event in the index page
 * [x] Generate a card for sharing event, with QRcode
 * [x] Map view, can catch all events in the Bay Area mapview.
 * [x] Map view: Each event pin on the map will be labeled "date + time + distance"
 * [x] Map view: shifting markers if overlapping (rotating 4 directions shifts, +polygon original->shifted)
 * [x] Add marker icons to upcoming events/future events/past events
 * [x] Map view: use more customizable maps -> Leaflet + openstreetmap
 * [x] Map view (Optional): cast routes of events on the map. To avoid overalpping of routes, display single route when hovering the marker.
 * [x] Support (cloud) comments for each event: commento.io
 * Allow event owner to cancel/edit details of the event.
 * Migrate events from MongoDB to local JSON file
 * Parse riding events from webpage (e.g. https://www.altovelo.org/c-ride)
 ## 2025-09-24 New Domain
 https://haoqiyou.info