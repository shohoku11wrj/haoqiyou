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

function initMap() {
    if (!window.map) { // Check if map is already initialized
        const centerLocation = [37.63, -122.23];
        window.map = L.map('map-container').setView(centerLocation, 10);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }).addTo(map);
    }

    events.map(event=>{
        var customIcon = null;
        customIcon = L.divIcon({
            className: 'custom-div-icon',
            html: buildMarkerIconHtml(event),
            iconSize: [32, 32], // Size of the icon
            iconAnchor: [16, event.event_time_type === 'upcoming' ? 32 : 30], // Point of the icon which will correspond to marker's location
            popupAnchor: [0, 0] // Point from which the popup should open relative to the iconAnchor
        });
        if (event.position) {
          var marker = L.marker([event.position.lat + event.shift[0], event.position.lng +  + event.shift[1]],
                                { icon: customIcon }).addTo(map);
          var routePolyline = getRoutePolylin(event.id);
          if (routePolyline) {
              marker.on('mouseover', function() {
                routePolyline.addTo(map);
              });

              marker.on('mouseout', function() {
                map.removeLayer(routePolyline);
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
          if (event.shift[0] != 0 || event.shift[1] != 0) {
              // Add a red dot at the original position
              var dot = L.circleMarker([event.position.lat, event.position.lng], {
                  radius: 5,
                  fillColor: "#ff0000",
                  color: "#ff0000",
                  weight: 1,
                  opacity: 1,
                  fillOpacity: 1
              }).addTo(map);

              // Add a red line from the original position to the shifted position
              var line = L.polyline([
                  [event.position.lat, event.position.lng],
                  [event.position.lat + event.shift[0], event.position.lng + event.shift[1]]
              ], {
                  color: "#ff0000",
                  weight: 3,
                  opacity: 0.5
              }).addTo(map);
          }
        }
    });
}
