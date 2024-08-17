# haoqiyou
HaoQiYou 好骑友 riding events whiteboard

## 2024-08-03 First Version
Release on https://haoqiyou.net

 * Step 1. Execute `update_strata_events.py` to fetch ride events from Strava to MongoDB
 * Step 2. Execute `load_html_script.py` to generate HTML into file `index.html`

TODO:
 * [x] Event detail page & event detail path for each event
 * [x] Share one event via event detail path, or generate a postcard for one event to share
 * [x] Simplify the index page, reduce layout size of each event so that events can be organized compactly (卡片式，瀑布式); hide some details of event in the index page
 * Map view, can catch all events in the Bay Area mapview. Each event pin on the map will be labeled "date + time + distance". Optional: cast routes of events on the map
 * Support (cloud) comments for each event
 * Allow event owner to cancel/edit details of the event.
 * Migrate events from MongoDB to local JSON file
 