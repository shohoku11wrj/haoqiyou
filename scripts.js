let currentPolyline = null; // Variable to store the current polyline
let currentSlideIndex = 0;
let slideIndex = 0;
// showSlides(slideIndex);

function getRoutePolyline(eventId) {
    var polylineElement = document.querySelector(`[data-event-id="${eventId}-route-polyline"]`);
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

function showEventDetailPopup(eventElement) {
    console.log("showEventDetailPopup");
    const eventId = eventElement.getAttribute('data-event-id');
    const eventDetails = document.getElementById(eventId).innerHTML;
    document.getElementById('popup-content').innerHTML = eventDetails;
    document.getElementById('popup-overlay').style.display = 'block';
    document.getElementById('popup').style.display = 'block';
    
    // Reset currentSlideIndex to 0 and update slides
    currentSlideIndex = 0;
    
    var routePolyline = getRoutePolyline(eventId);
    if (routePolyline) {
        // Remove existing polyline if there is one
        if (currentPolyline) {
            map.removeLayer(currentPolyline);
        }
        currentPolyline = routePolyline;
        currentPolyline.addTo(map);
    }
    // Update the URL
    history.pushState(null, '', `?id=${eventId}`);
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

function closePopupAndRemovePolyline() {
    console.log("closePopupAndRemovePolyline");
    document.getElementById('popup-overlay').style.display = 'none';
    document.getElementById('popup').style.display = 'none';
    document.getElementById('commento').style.display = 'none';
    // Remove the polyline when closing the popup
    if (currentPolyline) {
        map.removeLayer(currentPolyline);
    }
    // Remove the event ID from the URL
    history.pushState(null, '', window.location.pathname);
    
    // Reset currentSlideIndex to 0 and update slides
    currentSlideIndex = 0;
    const pictureCount = document.querySelectorAll('.slide').length;
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

function moveSlide(direction, pictureCount) {
    console.log("direction: " + direction);
    console.log("pictureCount: " + pictureCount);
    slides = document.querySelectorAll('.slide');
    dots = document.querySelectorAll('.dot');
    console.log("slides: " + slides.length);
    console.log("dots: " + dots.length);
    // TODO: fix the work around for the bug
    // Work around: there is a bug that actual pictures are at the end of the slides array.
    // Use the pictureCount to get the actual index of the picture.
    const slidesLength = slides.length;
    console.log("slidesLength: " + slidesLength);
    console.log("slidesLength - pictureCount: " + (slidesLength - pictureCount));
    slides = Array.from(slides).slice(slidesLength - pictureCount);
    dots = Array.from(dots).slice(slidesLength - pictureCount);
    console.log("sliced slides: " + slides.length);
    console.log("sliced dots: " + dots.length);
    
    currentSlideIndex += direction;
    console.log("currentSlideIndex: " + currentSlideIndex);
    
    // Handle wrapping
    if (currentSlideIndex >= slides.length) {
        currentSlideIndex = 0;
    }
    if (currentSlideIndex < 0) {
        currentSlideIndex = slides.length - 1;
    }
    
    // Show the current slide and hide others
    slides.forEach((slide, index) => {
        slide.style.display = index === currentSlideIndex ? 'block' : 'none';
    });
    
    // Update dots
    dots.forEach((dot, index) => {
        dot.classList.toggle('active', index === currentSlideIndex);
    });
}

function currentSlide(index, pictureCount) {
    currentSlideIndex = index;
    moveSlide(0, pictureCount); // Update display without moving
}

function showSlides(n) {
  console.log("showSlides: " + n);
  const slides = document.querySelectorAll('.slide');
  const dots = document.querySelectorAll('.dot');
  
  if (n >= slides.length) { slideIndex = 0 }
  if (n < 0) { slideIndex = slides.length - 1 }
  
  // Show the current slide and hide others
  slides.forEach((slide, index) => {
    slide.style.display = index === slideIndex ? 'block' : 'none';
  });
  
  // Update dots
  dots.forEach((dot, index) => {
    console.log("index: " + index);
    dot.classList.toggle('active', index === slideIndex);
  });
}

document.addEventListener('DOMContentLoaded', function() {
    initMap();

    document.getElementById("prod-link").addEventListener('click', function() {
        // get the current full path
        var currentPath = window.location.pathname;
        currentPath.replace("/dev", "");
        link.href = currentPath;
    });

    const toggleExtraElement = document.getElementById('toggleExtra');
    if (toggleExtraElement) {
        toggleExtraElement.addEventListener('change', function() {
            var extraEvents = document.querySelectorAll('.extra-event');
            extraEvents.forEach(function(event) {
                event.style.display = this.checked ? 'none' : 'block';
                event.style.backgroundColor = this.checked ? 'transparent' : '#cad6e6' ;
            }, this);
        });
    }

    document.querySelectorAll('.expand').forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            const fullDescription = this.getAttribute('data-full-description');
            this.parentElement.innerHTML = fullDescription;
        });
    });
    
    loadRelateiveDateForEvents();

    document.querySelectorAll('.event').forEach(function(eventDiv) {
        const eventId = eventDiv.getAttribute('data-event-id');
        var routePolyline = getRoutePolyline(eventId);
        if (routePolyline) {
            // Add mouseenter event listener
            eventDiv.addEventListener('mouseenter', function() {
                routePolyline.addTo(map);
            });

            // Add mouseleave event listener
            eventDiv.addEventListener('mouseleave', function() {
                map.removeLayer(routePolyline);
            });
        }

        eventDiv.addEventListener('click', function(event) {
            event.preventDefault();
            showEventDetailPopup(eventDiv);
        });
    });

    // Close button event listener
    document.getElementById('close-btn').addEventListener('click', closePopupAndRemovePolyline);

    // Popup overlay event listener
    document.getElementById('popup-overlay').addEventListener('click', closePopupAndRemovePolyline);

    
    document.querySelectorAll('.event-link').forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    });
  
    document.querySelectorAll("gmp-advanced-marker").forEach(function(advancedMarker){
        advancedMarker.addEventListener("gmp-click", (evt) => {
            showEventDetailPopup(advancedMarker);
        })
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
    // showSlides(slideIndex);
});
