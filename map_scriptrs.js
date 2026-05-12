function decodePolyline(str, precision) {
  var index = 0,
      lat = 0,
      lng = 0,
      coordinates = [],
      shift = 0,
      result = 0,
      byte = null,
      latitude_change,
      longitude_change,
      factor = Math.pow(10, precision || 5);

  while (index < str.length) {
    byte = null;
    shift = 0;
    result = 0;

    do {
      byte = str.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    latitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));
    shift = result = 0;

    do {
      byte = str.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    longitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));

    lat += latitude_change;
    lng += longitude_change;

    coordinates.push([lat / factor, lng / factor]);
  }

  return coordinates;
}

function getRoutePolylin(event_id) {
  var polylineElement = document.querySelector(`[data-event-id="${event_id}-route-polyline"]`);
  if (polylineElement) {
    var routePolyline = polylineElement.innerHTML.trim();
    if (routePolyline) {
        var latLngs = decodePolyline(routePolyline);
        return L.polyline(latLngs, {
            color: '#007bf6',
            weight: 4,
            opacity: 1.0
        });
      }
  }
  return null;
}

function buildMarkerIconHtml(event) {
    const iconUrl = event.icon_url;
    const markerBucket = event.past_marker_bucket || '';
    let sizeClass = '';

    if (markerBucket === 'past-31-90') {
        sizeClass = 'marker-icon-size-90';
    } else if (markerBucket === 'past-91-180') {
        sizeClass = 'marker-icon-size-75';
    } else if (markerBucket === 'past-181-plus') {
        sizeClass = 'marker-icon-size-60';
    }

    if (event.event_time_type === 'upcoming') {
        return `
        <div class="marker-icon-stack marker-icon-stack-upcoming">
            <img src="${iconUrl}" class="marker-icon-image" />
            <div class="tooltip-content marker-date-tooltip">
                ${event.date_span.month} <span class="marker-date-day">${event.date_span.day}</span>
            </div>
        </div>
        `;
    }

    if (markerBucket === 'past-31-90' || markerBucket === 'past-91-180') {
        const overlayClass = markerBucket === 'past-31-90'
            ? 'marker-icon-overlay-light'
            : 'marker-icon-overlay-medium';
        return `
        <div class="marker-icon-stack ${sizeClass}">
            <img src="${iconUrl}" class="marker-icon-image" />
            <img src="${iconUrl}" class="marker-icon-image ${overlayClass}" />
        </div>
        `;
    }

    const grayscaleClass = markerBucket === 'past-181-plus' ? 'marker-icon-grayscale' : '';
    return `
    <div class="marker-icon-stack ${sizeClass}">
        <img src="${iconUrl}" class="marker-icon-image ${grayscaleClass}" />
    </div>
    `;
}

function parseMarkerEventDate(value) {
    if (!value) {
        return null;
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getTwoMonthsAgo() {
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - 2);
    return cutoff;
}

function shouldHideOldPastMapEvent(event) {
    const toggleOldPastMapEvents = document.getElementById('toggleOldPastMapEvents');
    if (toggleOldPastMapEvents && toggleOldPastMapEvents.checked) {
        return false;
    }
    if (!event || event.event_time_type !== 'past') {
        return false;
    }

    const eventDate = parseMarkerEventDate(event.event_time_utc);
    if (eventDate) {
        return eventDate < getTwoMonthsAgo();
    }

    return event.past_marker_bucket === 'past-91-180' || event.past_marker_bucket === 'past-181-plus';
}

function shouldHideUnselectedMapEvent(event) {
    const toggleExtra = document.getElementById('toggleExtra');
    return Boolean(toggleExtra && toggleExtra.checked && event && event.is_extra_event);
}

function shouldHideMapEvent(event) {
    return shouldHideOldPastMapEvent(event) || shouldHideUnselectedMapEvent(event);
}

function initMapFilterToggles() {
    const toggleOldPastMapEvents = document.getElementById('toggleOldPastMapEvents');
    if (toggleOldPastMapEvents && toggleOldPastMapEvents.dataset.mapFilterAttached !== 'true') {
        toggleOldPastMapEvents.addEventListener('change', function() {
            renderEventMarkers();
        });
        toggleOldPastMapEvents.dataset.mapFilterAttached = 'true';
    }

    const toggleExtra = document.getElementById('toggleExtra');
    if (toggleExtra && toggleExtra.dataset.mapFilterAttached !== 'true') {
        toggleExtra.addEventListener('change', function() {
            renderEventMarkers();
        });
        toggleExtra.dataset.mapFilterAttached = 'true';
    }
}

function getMarkerPosition(event) {
    if (!event || !event.position) {
        return null;
    }
    const lat = Number(event.position.lat);
    const lng = Number(event.position.lng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
        return null;
    }
    return { lat, lng };
}

function assignVisibleMarkerShifts(visibleEvents) {
    const tolerance = 0.03;
    const shifts = [
        [0, 0],
        [0, -tolerance],
        [tolerance, 0],
        [0, tolerance],
        [-tolerance, 0],
        [tolerance, -tolerance],
        [tolerance, tolerance],
        [-tolerance, tolerance],
        [-tolerance, -tolerance]
    ];
    const groups = [];

    visibleEvents.forEach(function(event) {
        const position = getMarkerPosition(event);
        if (!position) {
            event.visibleShift = [0, 0];
            return;
        }

        let group = groups.find(function(item) {
            return Math.abs(item.lat - position.lat) < tolerance && Math.abs(item.lng - position.lng) < tolerance;
        });
        if (!group) {
            group = { lat: position.lat, lng: position.lng, events: [] };
            groups.push(group);
        }
        group.events.push(event);
    });

    groups.forEach(function(group) {
        group.events.forEach(function(event, index) {
            event.visibleShift = shifts[index % shifts.length];
        });
    });
}

function renderEventMarkers() {
    if (!window.map) {
        return;
    }
    if (window.currentHoveredRoutePolyline && window.map.hasLayer(window.currentHoveredRoutePolyline)) {
        window.map.removeLayer(window.currentHoveredRoutePolyline);
    }
    window.currentHoveredRoutePolyline = null;
    if (!window.eventMapLayerGroup) {
        window.eventMapLayerGroup = L.layerGroup().addTo(window.map);
    }
    window.eventMapLayerGroup.clearLayers();

    const visibleEvents = events.filter(function(event) {
        return !shouldHideMapEvent(event);
    });
    assignVisibleMarkerShifts(visibleEvents);

    visibleEvents.map(event=>{
        var customIcon = null;
        customIcon = L.divIcon({
            className: 'custom-div-icon',
            html: buildMarkerIconHtml(event),
            iconSize: [32, 32], // Size of the icon
            iconAnchor: [16, event.event_time_type === 'upcoming' ? 32 : 30], // Point of the icon which will correspond to marker's location
            popupAnchor: [0, 0] // Point from which the popup should open relative to the iconAnchor
        });
        if (event.position) {
          const shift = event.visibleShift || event.shift || [0, 0];
          var marker = L.marker([event.position.lat + shift[0], event.position.lng + shift[1]],
                                { icon: customIcon }).addTo(window.eventMapLayerGroup);
          var routePolyline = getRoutePolylin(event.id);
          if (routePolyline) {
              marker.on('mouseover', function() {
                window.currentHoveredRoutePolyline = routePolyline;
                routePolyline.addTo(map);
              });

              marker.on('mouseout', function() {
                if (map.hasLayer(routePolyline)) {
                    map.removeLayer(routePolyline);
                }
                if (window.currentHoveredRoutePolyline === routePolyline) {
                    window.currentHoveredRoutePolyline = null;
                }
              });
          }
          marker.bindTooltip(event.title, { className: 'custom-tooltip' });  //.openTooltip(); // by default, the tooltip is open
          marker.on('click', function() {
              const eventDetails = document.getElementById(event.id).innerHTML;
              document.getElementById('popup-content').innerHTML = eventDetails;
              document.getElementById('popup-overlay').style.display = 'block';
              document.getElementById('popup').style.display = 'block';
              var routePolyline = getRoutePolylin(event.id);
              if (routePolyline) {
                  // Remove existing polyline if there is one
                  if (currentPolyline) {
                      map.removeLayer(currentPolyline);
                  }
                  currentPolyline = routePolyline;
                  currentPolyline.addTo(map);
              }
              // Update the URL
              history.pushState(null, '', `?id=${event.id}`);
          });
          if (shift[0] != 0 || shift[1] != 0) {
              // Add a red dot at the original position
              var dot = L.circleMarker([event.position.lat, event.position.lng], {
                  radius: 5,
                  fillColor: "#ff0000",
                  color: "#ff0000",
                  weight: 1,
                  opacity: 1,
                  fillOpacity: 1
              }).addTo(window.eventMapLayerGroup);

              // Add a red line from the original position to the shifted position
              var line = L.polyline([
                  [event.position.lat, event.position.lng],
                  [event.position.lat + shift[0], event.position.lng + shift[1]]
              ], {
                  color: "#ff0000",
                  weight: 3,
                  opacity: 0.5
              }).addTo(window.eventMapLayerGroup);
          }
        }
    });
}

function initMap() {
    if (!window.map) { // Check if map is already initialized
        const centerLocation = [37.63, -122.23];
        window.map = L.map('map-container').setView(centerLocation, 10);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }).addTo(map);
    }
    initMapFilterToggles();
    renderEventMarkers();
}

document.addEventListener('DOMContentLoaded', initMapFilterToggles);
