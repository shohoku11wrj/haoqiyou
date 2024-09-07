function initMap() {
    if (!window.map) { // Check if map is already initialized
        const centerLocation = [37.53, -122.23];
        window.map = L.map('map-container').setView(centerLocation, 10);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }).addTo(map);
    }

    events.map(event=>{
        var customIcon = null;
        const iconElement = document.createElement('div');
        if (event.event_time_type != "upcoming") {
            customIcon = L.divIcon({
                className: 'custom-div-icon',
                html: `
                <div style='background-color:transparent;'>
                    <img src="${event.icon_url}" style="width: 100%; height: 100%; background-color: transparent" />
                </div>
                `,
                iconSize: [32, 32], // Size of the icon
                iconAnchor: [16, 30], // Point of the icon which will correspond to marker's location
                popupAnchor: [0, 0] // Point from which the popup should open relative to the iconAnchor
            });
        } else {
            customIcon = L.divIcon({
                className: 'custom-div-icon',
                html: `
                <div style="position: relative; width: 32px; height: 32px; background-color: transparent">
                    <div style='background-color:transparent;'>
                        <img src="${event.icon_url}" style="width: 100%; height: 100%; background-color: transparent" />
                    </div>
                    <div class="tooltip-content" style="position: absolute; top: -50%; left: 50%; transform: translate(-50%, -50%); padding: 5px, 0px; border-radius: 5px; text-align: center; white-space: nowrap; font-size: 15px;">
                        ${event.date_span.month} <span style="color: #fc5200">${event.date_span.day}</span>
                    </div>
                </div>
                `,
                iconSize: [32, 32], // Size of the icon
                iconAnchor: [16, 32], // Point of the icon which will correspond to marker's location
                popupAnchor: [0, 0] // Point from which the popup should open relative to the iconAnchor
            });
        }
        if (event.position) {
          var marker = L.marker([event.position.lat + event.shift[0], event.position.lng +  + event.shift[1]],
                                { icon: customIcon }).addTo(map);
          console.log(marker);
          marker.bindTooltip(event.title, { className: 'custom-tooltip' });  //.openTooltip(); // by default, the tooltip is open
          marker.on('click', function() {
              const eventDetails = document.getElementById(event.id).innerHTML;
              document.getElementById('popup-content').innerHTML = eventDetails;
              document.getElementById('popup-overlay').style.display = 'block';
              document.getElementById('popup').style.display = 'block';
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