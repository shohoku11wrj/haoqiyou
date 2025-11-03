(function () {
    const DATA_SOURCES = [
        'storage/events.json',
        'https://raw.githubusercontent.com/shohoku11wrj/haoqiyou/main/storage/events.json'
    ];
    const EXTRA_EVENT_GROUP_IDS = new Set([265, 908336, 1047313]);
    const DAY_OF_WEEK_MAP = {
        Monday: '周一',
        Tuesday: '周二',
        Wednesday: '周三',
        Thursday: '周四',
        Friday: '周五',
        Saturday: '周六',
        Sunday: '周日'
    };
    const TIME_ZONE = 'America/Los_Angeles';
    const GPS_OVERLAP_TOLERANCE = 0.03;
    const GPS_SHIFTS = [
        [0, 0],
        [0, -GPS_OVERLAP_TOLERANCE],
        [GPS_OVERLAP_TOLERANCE, 0],
        [0, GPS_OVERLAP_TOLERANCE],
        [-GPS_OVERLAP_TOLERANCE, 0],
        [GPS_OVERLAP_TOLERANCE, -GPS_OVERLAP_TOLERANCE],
        [GPS_OVERLAP_TOLERANCE, GPS_OVERLAP_TOLERANCE],
        [-GPS_OVERLAP_TOLERANCE, GPS_OVERLAP_TOLERANCE],
        [-GPS_OVERLAP_TOLERANCE, -GPS_OVERLAP_TOLERANCE]
    ];

    document.addEventListener('DOMContentLoaded', () => {
        loadEvents();
    });

    function loadEvents() {
        fetchWithFallback(DATA_SOURCES)
            .then((rawEvents) => {
                const normalized = rawEvents
                    .map(normalizeEvent)
                    .filter((event) => event && event.is_active && event.event_time_utc);
                const categorized = categorizeEvents(normalized);
                renderEventLists(categorized);
            })
            .catch((error) => {
                showError(error);
            });
    }

    function fetchWithFallback(urls, index = 0) {
        if (index >= urls.length) {
            return Promise.reject(new Error('无法加载活动数据'));
        }
        return fetch(urls[index])
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`请求失败: ${response.status}`);
                }
                return response.json();
            })
            .catch(() => fetchWithFallback(urls, index + 1));
    }

    function normalizeEvent(raw) {
        if (!raw) {
            return null;
        }
        const event = { ...raw };
        event._id = raw._id || '';
        event.source_type = raw.source_type || '';
        event.source_group_id = parseNumber(raw.source_group_id);
        event.source_group_name = raw.source_group_name || '';
        event.event_time_utc = parseDate(raw.event_time_utc);
        event.meet_up_location = normalizeText(raw.meet_up_location);
        event.gps_coordinates = normalizeText(raw.gps_coordinates);
        event.distance_meters = parseNumber(raw.distance_meters);
        event.elevation_gain_meters = parseNumber(raw.elevation_gain_meters);
        event.organizer = raw.organizer || '';
        event.title = raw.title || '';
        event.description = raw.description || '';
        event.route_map_url = raw.route_map_url || '';
        event.route_polyline = raw.route_polyline || '';
        event.event_picture_url = raw.event_picture_url || '';
        event.event_picture_urls = Array.isArray(raw.event_picture_urls) ? raw.event_picture_urls.filter(Boolean) : [];
        event.source_url = raw.source_url || '';
        event.route_url = raw.route_url || '';
        event.strava_url = raw.strava_url || '';
        event.expected_participants_number = raw.expected_participants_number || '';
        event.actual_participants_number = raw.actual_participants_number || '';
        event.is_active = raw.is_active !== false;
        return event;
    }

    function parseNumber(value) {
        if (value === null || value === undefined) {
            return 0;
        }
        if (typeof value === 'number') {
            return value;
        }
        if (typeof value === 'string' && value.trim() !== '') {
            const parsed = Number(value);
            return Number.isNaN(parsed) ? 0 : parsed;
        }
        if (typeof value === 'object' && value !== null) {
            if (Object.prototype.hasOwnProperty.call(value, '$numberLong')) {
                const parsed = Number(value.$numberLong);
                return Number.isNaN(parsed) ? 0 : parsed;
            }
            if (Object.prototype.hasOwnProperty.call(value, '$numberInt')) {
                const parsed = Number(value.$numberInt);
                return Number.isNaN(parsed) ? 0 : parsed;
            }
        }
        return 0;
    }

    function parseDate(value) {
        if (!value) {
            return null;
        }
        if (value instanceof Date) {
            return value;
        }
        if (typeof value === 'string') {
            const parsed = new Date(value);
            return Number.isNaN(parsed.getTime()) ? null : parsed;
        }
        if (typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, '$date')) {
            const parsed = new Date(value.$date);
            return Number.isNaN(parsed.getTime()) ? null : parsed;
        }
        return null;
    }

    function normalizeText(value) {
        if (typeof value === 'string') {
            return value.trim();
        }
        if (value === null || value === undefined) {
            return '';
        }
        return String(value).trim();
    }

    function categorizeEvents(events) {
        const now = new Date();
        const sixHoursBefore = new Date(now.getTime() - 6 * 60 * 60 * 1000);
        const fourteenDaysLater = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);
        const upcoming = [];
        const planning = [];
        const past = [];

        for (const event of events) {
            if (!event.event_time_utc) {
                continue;
            }
            const eventTime = event.event_time_utc;
            if (eventTime >= sixHoursBefore && eventTime <= fourteenDaysLater) {
                upcoming.push(event);
            } else if (eventTime > fourteenDaysLater) {
                planning.push(event);
            } else {
                past.push(event);
            }
        }

        upcoming.sort((a, b) => a.event_time_utc - b.event_time_utc);
        planning.sort((a, b) => a.event_time_utc - b.event_time_utc);
        past.sort((a, b) => b.event_time_utc - a.event_time_utc);

        return { upcoming, planning, past };
    }

    function renderEventLists(categories) {
        const listContainer = document.getElementById('list-container');
        if (!listContainer) {
            return;
        }

        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }

        const sections = [
            { type: 'upcoming', title: '<span style="opacity: 100;">U</span>Pcoming Events <img src="https://maps.google.com/mapfiles/ms/icons/green-dot.png" alt="Green Marker" />' },
            { type: 'planning', title: 'Planning Events <img src="https://maps.google.com/mapfiles/ms/icons/blue-dot.png" alt="Blue Marker" />' },
            { type: 'past', title: 'Past Events <img src="https://maps.google.com/mapfiles/ms/icons/yellow-dot.png" alt="Yellow Marker" />' }
        ];

        const htmlParts = [];
        const markerBuckets = [];

        for (const section of sections) {
            const events = categories[section.type] || [];
            htmlParts.push(`        <h2>${section.title}</h2>`);
            htmlParts.push('        <div class="events-container">');
            for (const event of events) {
                const parts = prepareEventParts(event, section.type);
                if (parts.marker) {
                    markerBuckets.push(parts.marker);
                }
                htmlParts.push(parts.html);
            }
            htmlParts.push('        </div>');
        }

        listContainer.innerHTML = htmlParts.join('\n');
        assignMarkerShifts(markerBuckets);
        window.events = markerBuckets.slice();
        refreshUpdatedTime();
        if (typeof initMap === 'function') {
            initMap();
        }
        hydrateNewContent();
    }

    function prepareEventParts(event, eventType) {
        const eventId = `event-${event._id}`;
        const timeParts = buildTimeParts(event.event_time_utc);
        const eventClass = EXTRA_EVENT_GROUP_IDS.has(event.source_group_id) ? 'extra-event' : 'selected-event';
        const gpsCoordinatesStr = event.gps_coordinates;
        const eventLocation = resolveEventLocation(event);
        const distanceStr = formatDistance(event.distance_meters);
        const elevationStr = formatElevation(event.elevation_gain_meters);
        const eventArea = deriveEventArea(gpsCoordinatesStr);
        const routeUrl = resolveRouteUrl(event);
        const sourceEventUrl = resolveSourceEventUrl(event, routeUrl);
        const sourceGroupName = resolveSourceGroupName(event);
        const descriptionHtml = convertUrlsToLinks(event.description || '');
        const popupHtml = buildPopupHtml({
            event,
            eventId,
            timeParts,
            eventType,
            gpsCoordinatesStr,
            eventLocation,
            distanceStr,
            elevationStr,
            routeUrl,
            sourceEventUrl,
            sourceGroupName,
            descriptionHtml
        });
        const distanceBlock = distanceStr ? `                    <span class="meet-up">总路程:</span> ${distanceStr} <br>` : '';
        const elevationBlock = elevationStr ? `                    <span class="meet-up">总爬坡:</span> ${elevationStr} <br>` : '';
        const expectedBlock = event.expected_participants_number && event.expected_participants_number !== '0'
            ? `                    <span class="meet-up">预计人数:</span> ${escapeHtml(event.expected_participants_number)} <br>`
            : '';
        const actualBlock = event.actual_participants_number && event.actual_participants_number !== '0'
            ? `                    <span class="meet-up">实际人数:</span> ${escapeHtml(event.actual_participants_number)} <br>`
            : '';
        const yearBlock = timeParts.showYear
            ? `                        <div class="year">${timeParts.year}</div>\n`
            : '';
        const areaBlock = eventArea
            ? `                    <div class="area-box">${eventArea}</div>\n`
            : '';
        const calendarBlock = (eventType === 'upcoming' || eventType === 'planning')
            ? `                    <div class="area-calendar-separator"></div>\n                    <div class="calendar-box" data-calendar-trigger="icon">\n                        <span class="material-symbols-outlined calendar-icon" aria-hidden="true">calendar_add_on</span>\n                    </div>\n`
            : '';

        const html = `        <div class="event ${eventClass}" data-event-id="${eventId}" data-event-title="${escapeAttribute(event.title)}" data-event-start="${timeParts.calendarStart}" data-event-end="${timeParts.calendarEnd}" data-event-location="${escapeAttribute(eventLocation)}" data-event-source-url="${escapeAttribute(sourceEventUrl)}">
            <a href="?id=${eventId}" class="event-link"></a>
            <div class="event-section">
${popupHtml}
                <div class="event-details">
                    <div class="date-box">
                        <div class="date">${timeParts.dayStr}</div>
                        <div class="month">${timeParts.monthStr}</div>
${yearBlock}                        <div class="date-relative" event-date="${timeParts.localIso}"></div>
${areaBlock}${calendarBlock}                    </div>
                    <div>
                        <strong>${timeParts.timeLabel}</strong> ${timeParts.dayOfWeekEn}<br>
                        <span class="meet-up">集合GPS:</span> ${escapeHtml(gpsCoordinatesStr)}
                    </div>
                </div>
                <div>
                    <span class="meet-up">集合地点:</span> ${escapeHtml(eventLocation)} <br>
${distanceBlock}${elevationBlock}${expectedBlock}${actualBlock}                </div>
            </div>
            <div class="event-section">
                ${event.route_map_url ? (routeUrl ? `<a href="${escapeAttribute(routeUrl)}" target="_blank" class="event-link">\n                    <img src="${escapeAttribute(event.route_map_url)}" alt="Route Image" width="100%">\n                </a>` : `<img src="${escapeAttribute(event.route_map_url)}" alt="Route Image" width="100%">`) : ''}
                <div data-event-id="${eventId}-route-polyline" style="display: none;">${event.route_polyline || ''}</div>
            </div>
            <div class="event-section">
                <div class="event-title">${escapeHtml(event.title)}</div> <br>
                <div class="event-description">发起人: ${escapeHtml(event.organizer)}</div> <br>
                <div class="event-description">活动来源: ${sourceEventUrl ? `<a href="${escapeAttribute(sourceEventUrl)}" target="_blank" class="event-link">${escapeHtml(sourceGroupName)}</a>` : escapeHtml(sourceGroupName)}</div>
            </div>
        </div>`;

        const marker = buildMarker(event, eventType, timeParts);
        return { html, marker };
    }

    function buildTimeParts(eventTimeUtc) {
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: TIME_ZONE,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
        const parts = formatter.formatToParts(eventTimeUtc).reduce((acc, part) => {
            acc[part.type] = part.value;
            return acc;
        }, {});

        const displayFormatter = new Intl.DateTimeFormat('en-US', {
            timeZone: TIME_ZONE,
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
        const dayOfWeekFormatter = new Intl.DateTimeFormat('en-US', {
            timeZone: TIME_ZONE,
            weekday: 'long'
        });
        const timeZoneFormatter = new Intl.DateTimeFormat('en-US', {
            timeZone: TIME_ZONE,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZoneName: 'shortOffset'
        });

        const day = parts.day || '01';
        const month = parts.month || '01';
        const year = Number(parts.year || eventTimeUtc.getUTCFullYear());
        const hour = parts.hour || '00';
        const minute = parts.minute || '00';
        const second = parts.second || '00';

        const dayOfWeekEn = dayOfWeekFormatter.format(eventTimeUtc);
        const timeLabel = displayFormatter.format(eventTimeUtc);

        const tzParts = timeZoneFormatter.formatToParts(eventTimeUtc);
        const tzNamePart = tzParts.find((part) => part.type === 'timeZoneName');
        let offset = '-00:00';
        if (tzNamePart && tzNamePart.value) {
            const match = tzNamePart.value.match(/GMT([+-]\d{1,2})(?::(\d{2}))?/i);
            if (match) {
                const hours = match[1].padStart(3, '0').replace('+-', '+');
                const minutes = match[2] || '00';
                offset = `${hours}:${minutes}`;
            }
        }

        const monthStr = new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: TIME_ZONE }).format(eventTimeUtc).toUpperCase();
        const dayStr = day.padStart(2, '0');
        const localIso = `${parts.year || eventTimeUtc.getUTCFullYear()}-${month}-${day} ${hour}:${minute}:${second}${offset}`;
        const calendarStart = buildCalendarTimestamp(eventTimeUtc);
        const calendarEnd = buildCalendarTimestamp(new Date(eventTimeUtc.getTime() + 3 * 60 * 60 * 1000));

        return {
            monthStr,
            dayStr,
            year,
            showYear: year !== new Date().getFullYear(),
            dayOfWeekEn,
            dayOfWeekCn: DAY_OF_WEEK_MAP[dayOfWeekEn] || dayOfWeekEn,
            timeLabel,
            localIso,
            calendarStart,
            calendarEnd
        };
    }

    function buildCalendarTimestamp(date) {
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        const seconds = String(date.getUTCSeconds()).padStart(2, '0');
        return `${year}${month}${day}T${hours}${minutes}${seconds}Z`;
    }

    function convertUrlsToLinks(text) {
        if (!text) {
            return '';
        }
        let result = text;
        const anchorPattern = /<a\s+href="([^"]+)"\s+target="_blank">[^<]+<\/a>/i;
        if (anchorPattern.test(result)) {
            return result;
        }
        const markdownPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
        result = result.replace(markdownPattern, '<a href="$2" target="_blank">$1</a>');
        const urlPattern = /(?<!href=")(https?:\/\/[^\s]+)/g;
        result = result.replace(urlPattern, '<a href="$1" target="_blank">$1</a>');
        return result;
    }

    function buildPopupHtml({ event, eventId, timeParts, eventType, gpsCoordinatesStr, eventLocation, distanceStr, elevationStr, routeUrl, sourceEventUrl, sourceGroupName, descriptionHtml }) {
        const yearBlock = timeParts.showYear ? `                    <div class="year">${timeParts.year}</div>\n` : '';
        const calendarBlock = (eventType === 'upcoming' || eventType === 'planning')
            ? `                <div class="calendar-box" data-calendar-trigger="icon">\n                    <span class="material-symbols-outlined calendar-icon" aria-hidden="true">calendar_add_on</span>\n                </div>\n                <div class="area-vertical-separator"></div>\n`
            : '';
        const pictureUrls = event.event_picture_urls && event.event_picture_urls.length > 0
            ? event.event_picture_urls
            : (event.event_picture_url ? [event.event_picture_url] : []);
        let pictureHtml = '';
        if (pictureUrls.length === 1) {
            pictureHtml += `            <a href="${escapeAttribute(sourceEventUrl || routeUrl)}" target="_blank" class="event-link">\n                <img src="${escapeAttribute(pictureUrls[0])}" alt="Event Image" width="100%">\n            </a>\n`;
        } else if (pictureUrls.length > 1) {
            pictureHtml += '            <div class="slideshow-container">\n';
            pictureHtml += `                <div class="slides-wrapper" slides-length="${pictureUrls.length}">\n`;
            pictureUrls.forEach((imgUrl, index) => {
                pictureHtml += `                    <div class="slide" data-index="${index}" style="${index === 0 ? 'display: block;' : 'display: none;'}">\n                        <a href="${escapeAttribute(imgUrl)}" target="_blank" class="event-link">\n                            <img src="${escapeAttribute(imgUrl)}" alt="Event Image ${index + 1}" class="slide-image">\n                        </a>\n                    </div>\n`;
            });
            pictureHtml += '                </div>\n';
            pictureHtml += `                <button class="slide-nav prev" onclick="moveSlide(-1, ${pictureUrls.length})">❮</button>\n                <button class="slide-nav next" onclick="moveSlide(1, ${pictureUrls.length})">❯</button>\n                <div class="slide-dots">\n`;
            pictureUrls.forEach((_, index) => {
                pictureHtml += `                    <span class="dot" onclick="currentSlide(${index}, ${pictureUrls.length})"></span>\n`;
            });
            pictureHtml += '                </div>\n';
            pictureHtml += '            </div>\n';
        }

        const distanceBlock = distanceStr ? `            <p><strong>总路程::</strong> ${distanceStr}</p>\n` : '';
        const elevationBlock = elevationStr ? `            <p><strong>总爬坡:</strong> ${elevationStr}</p>\n` : '';
        const expectedBlock = event.expected_participants_number && event.expected_participants_number !== '0'
            ? `        <p><strong>预计人数:</strong> ${escapeHtml(event.expected_participants_number)}</p>\n`
            : '';
        const actualBlock = event.actual_participants_number && event.actual_participants_number !== '0'
            ? `        <p><strong>实际人数:</strong> ${escapeHtml(event.actual_participants_number)}</p>\n`
            : '';

        const routeMapImg = event.route_map_url
            ? `<img src="${escapeAttribute(event.route_map_url)}" alt="Route Image" width="100%">`
            : '';
        const locationBlock = eventLocation ? `            <p><strong>集合地点:</strong> ${escapeHtml(eventLocation)}</p>\n` : '';

        return `        <div id="${eventId}" style="display: none;">
            <div class="event-title-row">
                <div class="date-box">
                    <div class="date">${timeParts.dayStr}</div>
                    <div class="month">${timeParts.monthStr}</div>
                    <div class="day-of-week">${timeParts.dayOfWeekCn}</div>
${yearBlock}                </div>
${calendarBlock}                <div class="event-title">${escapeHtml(event.title)}</div>
            </div>
            <p class="event-description">${descriptionHtml}</p>
${pictureHtml}${routeMapImg ? `${routeUrl ? `<a href="${escapeAttribute(routeUrl)}" target="_blank" class="event-link">` : ''}
                ${routeMapImg}
            ${routeUrl ? '</a>' : ''}` : ''}
            <p><strong>时间:</strong> ${timeParts.timeLabel}, ${timeParts.dayOfWeekEn}, ${timeParts.monthStr} ${timeParts.dayStr}, ${timeParts.year}</p>
            <p><strong>集合GPS:</strong> ${escapeHtml(gpsCoordinatesStr)}</p>
${locationBlock}${distanceBlock}${elevationBlock}        <p><strong>发起人:</strong> ${escapeHtml(event.organizer)}</p>
        <p><strong>活动来源:</strong> ${sourceEventUrl ? `<a href="${escapeAttribute(sourceEventUrl)}" target="_blank">${escapeHtml(sourceGroupName)}</a>` : escapeHtml(sourceGroupName)}</p>
${expectedBlock}${actualBlock}        </div>`;
    }

    function resolveEventLocation(event) {
        if (!event) {
            return '';
        }
        const meetupValue = normalizeText(event.meet_up_location);
        if (meetupValue) {
            return meetupValue;
        }
        return normalizeText(event.gps_coordinates);
    }

    function deriveEventArea(gpsCoordinatesStr) {
        if (!gpsCoordinatesStr) {
            return '';
        }
        const parts = gpsCoordinatesStr.split(',').map((value) => Number(value.trim()));
        if (parts.length !== 2 || parts.some((value) => Number.isNaN(value))) {
            return '';
        }
        const [lat, lng] = parts;
        if (lat >= 35 && lat <= 40 && lng >= -123.3 && lng <= -119.5) {
            return '北加';
        }
        if (lat >= 32 && lat <= 35 && lng >= -120 && lng <= -114) {
            return '南加';
        }
        return '';
    }

    function resolveRouteUrl(event) {
        if (event.route_url) {
            return event.route_url;
        }
        if (event.strava_url) {
            return event.strava_url;
        }
        if (event.source_url && event.source_url.startsWith('http')) {
            return event.source_url;
        }
        return '';
    }

    function resolveSourceEventUrl(event, routeUrl) {
        if (event.source_url) {
            return event.source_url;
        }
        return routeUrl;
    }

    function resolveSourceGroupName(event) {
        if (event.source_type === 'strava') {
            return `Strava Club - ${event.source_group_name}`;
        }
        if (event.source_type === 'wechat') {
            return `微信群 - ${event.source_group_name}`;
        }
        if (event.source_type === 'news') {
            return `新闻 - ${event.source_group_name}`;
        }
        return event.source_group_name;
    }

    function formatDistance(distanceMeters) {
        if (!distanceMeters || distanceMeters <= 0) {
            return '';
        }
        const km = distanceMeters / 1000;
        const miles = km * 0.621371;
        return `${km.toFixed(2)} km (${miles.toFixed(2)} miles)`;
    }

    function formatElevation(elevationMeters) {
        if (!elevationMeters || elevationMeters <= 0) {
            return '';
        }
        const feet = elevationMeters * 3.28084;
        return `${Math.round(elevationMeters).toLocaleString()} m (${Math.round(feet).toLocaleString()} ft)`;
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeAttribute(value) {
        return escapeHtml(value).replace(/\n/g, ' ');
    }

    function buildMarker(event, eventType, timeParts) {
        const gpsCoordinatesStr = event.gps_coordinates || '';
        const parts = gpsCoordinatesStr.split(',').map((value) => Number(value.trim()));
        if (parts.length !== 2 || parts.some((value) => Number.isNaN(value))) {
            return null;
        }
        const [lat, lng] = parts;
        const iconMap = {
            upcoming: 'https://maps.google.com/mapfiles/ms/icons/green-dot.png',
            planning: 'https://maps.google.com/mapfiles/ms/icons/blue-dot.png',
            past: 'https://maps.google.com/mapfiles/ms/icons/yellow-dot.png'
        };
        const marker = {
            title: `${timeParts.monthStr} ${timeParts.dayStr}: ${event.title}`,
            date_span: { month: timeParts.monthStr, day: timeParts.dayStr },
            position: { lat, lng },
            shift: [0, 0],
            id: `event-${event._id}`,
            icon_url: iconMap[eventType] || 'https://maps.google.com/mapfiles/ms/icons/red-dot.png',
            event_time_type: eventType
        };
        return marker;
    }

    function assignMarkerShifts(markers) {
        const groups = [];
        markers
            .filter(Boolean)
            .forEach((marker) => {
                const { lat, lng } = marker.position;
                let group = groups.find((item) => Math.abs(item.lat - lat) < GPS_OVERLAP_TOLERANCE && Math.abs(item.lng - lng) < GPS_OVERLAP_TOLERANCE);
                if (!group) {
                    group = { lat, lng, markers: [] };
                    groups.push(group);
                }
                group.markers.push(marker);
            });
        groups.forEach((group) => {
            group.markers.forEach((marker, index) => {
                const shift = GPS_SHIFTS[index % GPS_SHIFTS.length];
                marker.shift = shift;
            });
        });
    }

    function hydrateNewContent() {
        if (typeof loadRelateiveDateForEvents === 'function') {
            loadRelateiveDateForEvents();
        }
        if (typeof attachCalendarHandlers === 'function') {
            attachCalendarHandlers();
        }

        const toggleExtraElement = document.getElementById('toggleExtra');
        if (toggleExtraElement && toggleExtraElement.checked) {
            document.querySelectorAll('.extra-event').forEach((eventElement) => {
                eventElement.style.display = 'none';
                eventElement.style.backgroundColor = 'transparent';
            });
        }

        document.querySelectorAll('.event').forEach((eventElement) => {
            if (eventElement.dataset.interactionsAttached === 'true') {
                return;
            }
            const eventId = eventElement.getAttribute('data-event-id');
            const routePolyline = typeof getRoutePolyline === 'function' ? getRoutePolyline(eventId) : null;
            if (routePolyline) {
                eventElement.addEventListener('mouseenter', () => {
                    const mapInstance = window.map;
                    if (mapInstance) {
                        routePolyline.addTo(mapInstance);
                    }
                });
                eventElement.addEventListener('mouseleave', () => {
                    const mapInstance = window.map;
                    if (mapInstance && mapInstance.hasLayer(routePolyline)) {
                        mapInstance.removeLayer(routePolyline);
                    }
                });
            }
            eventElement.addEventListener('click', (evt) => {
                evt.preventDefault();
                if (typeof showEventDetailPopup === 'function') {
                    showEventDetailPopup(eventElement);
                }
            });
            eventElement.dataset.interactionsAttached = 'true';
        });

        document.querySelectorAll('.event-link').forEach((link) => {
            if (link.dataset.linkHandlerAttached === 'true') {
                return;
            }
            const href = link.getAttribute('href') || '';
            const isExternal = link.target === '_blank' || href.startsWith('http');
            if (isExternal) {
                link.addEventListener('click', (event) => {
                    event.stopPropagation();
                });
            }
            link.dataset.linkHandlerAttached = 'true';
        });

        const urlParams = new URLSearchParams(window.location.search);
        const pendingEventId = urlParams.get('id');
        if (pendingEventId) {
            const target = document.querySelector(`[data-event-id="${pendingEventId}"]`);
            if (target && typeof showEventDetailPopup === 'function') {
                showEventDetailPopup(target);
            }
        }
    }

    function refreshUpdatedTime() {
        const updatedElement = document.getElementById('updated-time');
        if (!updatedElement) {
            return;
        }
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: TIME_ZONE,
            month: '2-digit',
            day: '2-digit',
            year: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
        updatedElement.textContent = `Updated on ${formatter.format(new Date())}`;
    }

    function showError(error) {
        const listContainer = document.getElementById('list-container');
        if (listContainer) {
            listContainer.innerHTML = `<div class="error">无法加载活动数据: ${escapeHtml(error.message || error)}</div>`;
        }
        const updatedElement = document.getElementById('updated-time');
        if (updatedElement) {
            updatedElement.textContent = 'Updated on --';
        }
        console.error(error);
    }
})();
