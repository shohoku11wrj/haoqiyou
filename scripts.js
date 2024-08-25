
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('toggleExtra').addEventListener('change', function() {
        var extraEvents = document.querySelectorAll('.extra-event');
        extraEvents.forEach(function(event) {
            event.style.display = this.checked ? 'none' : 'block';
            event.style.backgroundColor = this.checked ? 'transparent' : '#cad6e6' ;
        }, this);
    });

    document.querySelectorAll('.expand').forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            const fullDescription = this.getAttribute('data-full-description');
            this.parentElement.innerHTML = fullDescription;
        });
    });
    
    loadRelateiveDateForEvents();

    document.querySelectorAll('.event').forEach(function(eventDiv) {
        eventDiv.addEventListener('click', function(event) {
            event.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            const eventDetails = document.getElementById(eventId).innerHTML;
            document.getElementById('popup-content').innerHTML = eventDetails;
            document.getElementById('popup-overlay').style.display = 'block';
            document.getElementById('popup').style.display = 'block';
            // Update the URL
            history.pushState(null, '', `?id=${eventId}`);
        });
    });

    document.querySelectorAll('.event-link').forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    });
  
    document.querySelectorAll("gmp-advanced-marker").forEach(function(advancedMarker){
        advancedMarker.addEventListener("gmp-click", (evt) => {
            const eventId = advancedMarker.getAttribute('data-event-id');
            const eventDetails = document.getElementById(eventId).innerHTML;
            document.getElementById('popup-content').innerHTML = eventDetails;
            document.getElementById('popup-overlay').style.display = 'block';
            document.getElementById('popup').style.display = 'block';
        })
    });

    document.getElementById('close-btn').addEventListener('click', function() {
        document.getElementById('popup-overlay').style.display = 'none';
        document.getElementById('popup').style.display = 'none';
        document.getElementById('commento').style.display = 'none';
        // Remove the event ID from the URL
        history.pushState(null, '', window.location.pathname);
    });

    document.getElementById('popup-overlay').addEventListener('click', function() {
        document.getElementById('popup-overlay').style.display = 'none';
        document.getElementById('popup').style.display = 'none';
        document.getElementById('commento').style.display = 'none';
        // Remove the event ID from the URL
        history.pushState(null, '', window.location.pathname);
    });

    
    // Check for URL parameter and open popup if it exists
    const urlParams = new URLSearchParams(window.location.search);
    const eventId = urlParams.get('id');
    if (eventId) {
        const eventElement = document.querySelector(`[data-event-id="${eventId}"]`);
        if (eventElement) {
            showEventDetailPopup(eventElement);
        }
    }

    // Add event listener to the hyperlink
    document.getElementById('load-commento-link').addEventListener('click', function(event) {
        event.preventDefault(); // Prevent the default link behavior
        // Extract the 'id' parameter from the URL
        const eventId = getParameterByName('id');
        // Load Commento with the extracted eventId
        if (eventId) {
            loadCommento(eventId);
        }
    });
});

function showEventDetailPopup(eventElement) {
  const eventId = eventElement.getAttribute('data-event-id');
  const eventDetails = document.getElementById(eventId).innerHTML;
  document.getElementById('popup-content').innerHTML = eventDetails;
  document.getElementById('popup-overlay').style.display = 'block';
  document.getElementById('popup').style.display = 'block';
}

function loadRelateiveDateForEvents() {
  document.querySelectorAll('.date-relative').forEach(function(dateRelativeDiv) {
      const eventDateStr = dateRelativeDiv.getAttribute('event-date');
      // convert to Date object
      const eventDateObj = new Date(eventDateStr);
      const currentDate = new Date();
      // Normalize both dates to midnight
      eventDateObj.setHours(0, 0, 0, 0);
      currentDate.setHours(0, 0, 0, 0);
      const oneDay = 24 * 60 * 60 * 1000;
      const diffDays = Math.round((eventDateObj - currentDate) / oneDay);

      let label = '';

      if (diffDays === 0) {
          label = '今天';
      } else if (diffDays === 1) {
          label = '明天';
      } else if (diffDays === 2) {
          label = '后天';
      } else if (diffDays === -1) {
          label = '昨天';
      }

      if (label) {
          dateRelativeDiv.innerHTML = label;
      }
  });
}

// Function to get URL parameter by name
function getParameterByName(name, url = window.location.href) {
  name = name.replace(/[\[\]]/g, '\\$&');
  const regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)');
  const results = regex.exec(url);
  if (!results) return null;
  if (!results[2]) return '';
  return decodeURIComponent(results[2].replace(/\+/g, ' '));
}

// Function to load Commento
function loadCommento(eventId) {
  // Create a new Commento script element
  const script = document.createElement('script');
  script.id = 'commento-js';
  script.defer = true;
  script.src = 'https://cdn.commento.io/js/commento.js';
  script.setAttribute('data-page-id', eventId);

  // Append the new script element to the commento div
  document.getElementById('commento').innerHTML = '';
  document.getElementById('commento').appendChild(script);
  document.getElementById('commento').style.display = 'block';
}