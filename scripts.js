let currentPolyline = null; // Variable to store the current polyline
let currentSlideIndex = 0;
let slideIndex = 0;
// showSlides(slideIndex);
const LIST_VISIBILITY_STORAGE_KEY = 'haoqiyou:listHidden';

function safeGetListVisibility() {
    try {
        return localStorage.getItem(LIST_VISIBILITY_STORAGE_KEY);
    } catch (error) {
        console.warn('Unable to access localStorage for list visibility preference.', error);
        return null;
    }
}

function safeSetListVisibility(value) {
    try {
        localStorage.setItem(LIST_VISIBILITY_STORAGE_KEY, value);
    } catch (error) {
        console.warn('Unable to persist list visibility preference.', error);
    }
}

function invalidateMapSize() {
    if (window.map && typeof window.map.invalidateSize === 'function') {
        window.map.invalidateSize();
    }
}

function normaliseEventDateString(value) {
    if (!value) {
        return '';
    }
    const trimmed = value.trim();
    if (!trimmed) {
        return '';
    }
    return trimmed.includes('T') ? trimmed : trimmed.replace(' ', 'T');
}

function parseEventDate(value) {
    const normalised = normaliseEventDateString(value);
    if (!normalised) {
        return null;
    }
    const parsed = new Date(normalised);
    if (!Number.isNaN(parsed.getTime())) {
        return parsed;
    }

    const icalMatch = normalised.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?$/);
    if (icalMatch) {
        const [_, y, m, d, hh, mm, ss, z] = icalMatch;
        const year = Number.parseInt(y, 10);
        const month = Number.parseInt(m, 10) - 1;
        const day = Number.parseInt(d, 10);
        const hour = Number.parseInt(hh, 10);
        const minute = Number.parseInt(mm, 10);
        const second = Number.parseInt(ss, 10);
        if (z) {
            return new Date(Date.UTC(year, month, day, hour, minute, second));
        }
        return new Date(year, month, day, hour, minute, second);
    }

    return null;
}

function formatDateForCalendar(date) {
    const pad = (num) => String(num).padStart(2, '0');
    return `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`;
}

function getTextContentAfterSpan(span) {
    if (!span) {
        return '';
    }
    let node = span.nextSibling;
    let buffer = '';
    while (node) {
        if (node.nodeType === Node.TEXT_NODE) {
            buffer += node.textContent;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.tagName === 'BR') {
                break;
            }
            break;
        }
        node = node.nextSibling;
    }
    return buffer.trim();
}

function extractLocationFromEvent(eventElement, dataset) {
    if (dataset && dataset.eventLocation) {
        return dataset.eventLocation;
    }
    const locationLabel = '集合地点';
    const meetUpSpans = eventElement.querySelectorAll('.meet-up');
    for (const span of meetUpSpans) {
        if (span.textContent && span.textContent.trim().startsWith(locationLabel)) {
            const location = getTextContentAfterSpan(span);
            if (location) {
                return location;
            }
        }
    }
    return '';
}

function findSourceLink(eventElement) {
    const sourceLink = eventElement.querySelector('.event-description a[href]');
    return sourceLink ? sourceLink.href : '';
}

function buildCalendarDetails(eventElement, dataset, eventId) {
    const detailParts = [];
    let sourceUrl = dataset ? dataset.eventSourceUrl : '';
    if (!sourceUrl) {
        sourceUrl = findSourceLink(eventElement) || '';
    }

    if (eventId) {
        const hiddenDetail = document.getElementById(eventId);
        if (hiddenDetail) {
            const descriptions = hiddenDetail.querySelectorAll('.event-description');
            const descriptionText = Array.from(descriptions)
                .map((node) => node.textContent.trim())
                .filter(Boolean)
                .join('\n\n');
            if (descriptionText) {
                detailParts.push(descriptionText);
            }
        }
    }

    const meetUpInfo = Array.from(eventElement.querySelectorAll('.meet-up'))
        .map((span) => {
            const label = span.textContent ? span.textContent.trim() : '';
            const value = getTextContentAfterSpan(span);
            return label && value ? `${label} ${value}` : '';
        })
        .filter(Boolean);
    if (meetUpInfo.length) {
        detailParts.push(meetUpInfo.join('\n'));
    }

    if (sourceUrl) {
        detailParts.push(`活动链接: ${sourceUrl}`);
    }

    if (eventId) {
        const eventPageUrl = new URL(window.location.origin + window.location.pathname);
        eventPageUrl.searchParams.set('id', eventId);
        detailParts.push(`活动页面: ${eventPageUrl.toString()}`);
    }

    return {
        text: detailParts.filter(Boolean).join('\n\n'),
        sourceUrl,
    };
}

function buildGoogleCalendarUrl(eventElement) {
    if (!eventElement) {
        return null;
    }
    const dataset = eventElement.dataset || {};
    const eventId = dataset.eventId || eventElement.getAttribute('data-event-id') || '';

    const dateRelativeElement = eventElement.querySelector('.date-relative');
    const startSource = dataset.eventStart || (dateRelativeElement ? dateRelativeElement.getAttribute('event-date') : '');
    const startDate = parseEventDate(startSource);
    if (!startDate) {
        console.warn('Unable to determine event start time for Google Calendar export.', eventElement);
        return null;
    }

    const durationMinutes = dataset.eventDurationMinutes ? Number.parseInt(dataset.eventDurationMinutes, 10) : NaN;
    let endDate = parseEventDate(dataset.eventEnd);
    if (!endDate) {
        const fallbackMinutes = Number.isFinite(durationMinutes) && durationMinutes > 0 ? durationMinutes : 180;
        endDate = new Date(startDate.getTime() + fallbackMinutes * 60 * 1000);
    }

    const title = (dataset.eventTitle || '').trim() || (eventElement.querySelector('.event-title')?.textContent.trim()) || '骑行活动';
    const location = extractLocationFromEvent(eventElement, dataset);
    const details = buildCalendarDetails(eventElement, dataset, eventId);

    const calendarUrl = new URL('https://calendar.google.com/calendar/render');
    calendarUrl.searchParams.set('action', 'TEMPLATE');
    calendarUrl.searchParams.set('text', title);
    calendarUrl.searchParams.set('dates', `${formatDateForCalendar(startDate)}/${formatDateForCalendar(endDate)}`);
    if (location) {
        calendarUrl.searchParams.set('location', location);
    }
    if (details.text) {
        calendarUrl.searchParams.set('details', details.text);
    }
    if (details.sourceUrl) {
        calendarUrl.searchParams.set('sprop', `website:${details.sourceUrl}`);
    }
    calendarUrl.searchParams.set('trp', 'false');

    return calendarUrl.toString();
}

function attachCalendarHandlers() {
    const calendarBoxes = document.querySelectorAll('.calendar-box');
    calendarBoxes.forEach((box) => {
        const eventElement = box.closest('.event');
        if (!eventElement) {
            return;
        }

        if (!box.hasAttribute('tabindex')) {
            box.setAttribute('tabindex', '0');
        }
        if (!box.hasAttribute('role')) {
            box.setAttribute('role', 'button');
        }
        if (!box.hasAttribute('aria-label')) {
            box.setAttribute('aria-label', '添加到 Google 日历');
        }

        const activate = (event) => {
            event.preventDefault();
            event.stopPropagation();
            const calendarUrl = buildGoogleCalendarUrl(eventElement);
            if (calendarUrl) {
                window.open(calendarUrl, '_blank', 'noopener,noreferrer');
            }
        };

        box.addEventListener('click', activate);
        box.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                activate(event);
            }
        });
    });
}

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

    const pageContainer = document.getElementById('page-container');
    const listContainer = document.getElementById('list-container');
    const toggleListButton = document.getElementById('toggle-list-btn');
    const largeScreenQuery = window.matchMedia('(min-width: 1000px)');

    if (pageContainer && listContainer && toggleListButton) {
        const hideText = toggleListButton.dataset.hideText || '隐藏活动列表';
        const showText = toggleListButton.dataset.showText || '显示活动列表';

        const applyListVisibility = (hidden) => {
            pageContainer.classList.toggle('list-hidden', hidden);
            toggleListButton.textContent = hidden ? showText : hideText;
            toggleListButton.setAttribute('aria-pressed', hidden ? 'true' : 'false');
            if (hidden) {
                listContainer.setAttribute('aria-hidden', 'true');
            } else {
                listContainer.removeAttribute('aria-hidden');
            }
            safeSetListVisibility(hidden ? '1' : '0');
            requestAnimationFrame(invalidateMapSize);
        };

        const enforceLayoutForScreen = () => {
            if (!largeScreenQuery.matches) {
                pageContainer.classList.remove('list-hidden');
                listContainer.removeAttribute('aria-hidden');
                toggleListButton.textContent = hideText;
                toggleListButton.setAttribute('aria-pressed', 'false');
                requestAnimationFrame(invalidateMapSize);
                return;
            }

            const storedVisibility = safeGetListVisibility();
            applyListVisibility(storedVisibility === '1');
        };

        enforceLayoutForScreen();

        const handleMediaChange = () => {
            enforceLayoutForScreen();
        };

        if (typeof largeScreenQuery.addEventListener === 'function') {
            largeScreenQuery.addEventListener('change', handleMediaChange);
        } else if (typeof largeScreenQuery.addListener === 'function') {
            largeScreenQuery.addListener(handleMediaChange);
        }

        toggleListButton.addEventListener('click', function() {
            if (!largeScreenQuery.matches) {
                return;
            }
            const willHide = !pageContainer.classList.contains('list-hidden');
            applyListVisibility(willHide);
        });
    }

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

    const eventElements = document.querySelectorAll('.event');
    console.log(`Strava events loaded: ${eventElements.length}`);

    eventElements.forEach(function(eventDiv) {
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

    attachCalendarHandlers();

    // Close button event listener
    document.getElementById('close-btn').addEventListener('click', closePopupAndRemovePolyline);

    // Popup overlay event listener
    document.getElementById('popup-overlay').addEventListener('click', closePopupAndRemovePolyline);

    
    document.querySelectorAll('.event-link').forEach(function(link) {
        const href = link.getAttribute('href') || '';
        const isExternalLink = link.target === '_blank' || href.startsWith('http');

        if (isExternalLink) {
            link.addEventListener('click', function(event) {
                event.stopPropagation();
            });
        }
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
