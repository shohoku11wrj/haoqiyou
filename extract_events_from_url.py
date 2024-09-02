import json
import google.generativeai as genai
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up OpenAI API key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Calculate the cutoff date (two weeks ago from today)
CUTOFF_DATE = datetime.now() - timedelta(weeks=2)

def extract_detail_feilds(html_content):
    fields_prompt_map = {
        'organizer: ': '<strong>Ride Leader</strong>: John<strong>. Expected Value: John',
        'meetup_time: ': 'The start time of the event. For example: given the text of "Time:  Saturday, gather at 9am. rolling by 9:15am". Expected Value: 09:00',
    }
    prompt = f"Extract the following fields ${fields_prompt_map.keys} about riding event from the following text:\n```\n{html_content}\n```\nHere are some examples of the fields and their context to extract:\n"
    for field, context in fields_prompt_map.items():
        prompt += f"Field: {field}, Context: {context}\n"
    prompt += '\nThe output should be json format, for example:\n{"organizer": "John", "meetup_time": "09:00"}\n'
    prompt += '\nFor each riding event, just generate the ${fields_prompt_map.keys} fields.\n'

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        # response = genai.generate_text(
        #     model="models/gemini-1.5-flash-001",
        #     prompt=prompt,
        #     temperature=1,
        #     max_output_tokens=100
        # )
        # Process the response
        if response.text:
            print("response", response.text)
        else:
            # Handle potential errors gracefully
            print(f"Error: {response.error}")
        # Example response: response ```json\n{"organizer": "John", "meetup_time": "09:00"}\n```
        ai_response = response.text.strip()
        response_json = ai_response.split('json\n')[1].strip()
        return response_json
        # return {
        #     'organizer': ai_response.split('organizer: ')[1].split('\n')[0].strip(),
        #     'meetup_time': ai_response.split('meetup_time: ')[1].strip()
        # }
    except Exception as e:
        print("Error extracting details: ", e)
        return {}


def fetch_events(url):
    response = requests.get(url)
    response.raise_for_status()  # Ensure we notice bad responses
    return response.text

def parse_single_event(event):
    html_content = fetch_events(event['source_url'])
    soup = BeautifulSoup(html_content, 'html.parser')
    # Extract event details
    description_tag = soup.find('div', class_='sqs-html-content')
    time_tag = description_tag.find('strong', text='Time: ')
    organizer_tag = description_tag.find('strong', text='Ride Leader')
    # the organize name is in a text right after the organizer tag
    # sometimes start with ": " or " - ", so we need to strip the leading characters
    organizer_name = organizer_tag.next_sibling.lstrip(':').lstrip('-').strip() if organizer_tag else 'Alto Velo members'
    # the href should start with "https://www.strava.com/routes/"
    # for example" <a href="https://www.strava.com/routes/3264481791722414714" target="_blank"><strong>&nbsp;OLH &amp; W-OLH + Joaquin</strong></a>
    # route_map_tag = description_tag.find('a', href=True, text=True)
    # the meet up location tag should be a link to google maps
    # for example: <a href="https://maps.app.goo.gl/emgD6hdD9fLTaJch6"><strong><em>Summit Bicycles</em>&nbsp;</strong></a>
    # meet_up_location_tag = description_tag.find('a', href=True, text=True)
    # event.date sample: 8/21/24, event.time sample: 9am

    # Extract specific details from the description
    date_time_str = ''
    start_location = ''
    strava_url = ''
    ride_leader = ''

    if description_tag:
        for p in description_tag.find_all('p'):
            text = p.get_text(strip=True)
            if 'Time:' in text:
                date_time_str = text.split('Time:')[1].strip()
            if 'Start:' in text:
                start_location = p.find('a')['href'] if p.find('a') and 'maps.app.goo.gl' in p.find('a')['href'] else text.split('Start:')[1].strip()
            if 'Route Link:' in text or ('strava.com/routes' in p.find('a')['href'] if p.find('a') else ''):
                strava_url = p.find('a')['href'] if p.find('a') and 'strava.com/routes' in p.find('a')['href'] else ''
            if 'Ride Leader' in text:
                ride_leader = text.split('Ride Leader:')[1].strip()

    # Extract the event details using AI
    detail_feilds = extract_detail_feilds(description_tag)
    # Example: {"organizer": "John", "meetup_time": "09:00"}
    print("Extracted details: ", detail_feilds)
    # Parse the string to json
    detail_feilds = json.loads(detail_feilds)
    ride_leader = detail_feilds['organizer'] if 'organizer' in detail_feilds else ride_leader
    event_time_str = event['date'] + detail_feilds['meetup_time'] +':00.000-07:00'

    event_details = {
        'source_type': 'webpage',
        'source_event_id': {
            '$numberLong': '2024083109000001'  # Example ID, you may need to generate this dynamically
        },
        'source_group_id': {
            '$numberLong': '1047313'  # Alto Velo C Ride group ID
        },
        'description': '',
        'distance_meters': 0,
        'elevation_gain_meters': 0,
        'event_time_utc': {
            '$date': event_time_str
        },
        'gps_coordinates': '37.426627, -122.144647',  # Example coordinates, you may need to extract this dynamically
        'is_active': True,
        'meet_up_location': start_location,
        'organizer': detail_feilds['organizer'] if 'organizer' in detail_feilds else ride_leader,
        'strava_url': strava_url,
        'source_group_name': 'Alto Velo C Ride',
        'title': event['title'],
        'source_url': event['source_url']
    }

    return event_details

def parse_event_details(events_list):
    event_details_list = []
    for event in events_list:
        single_event_detail = parse_single_event(event)
        event_details_list.append(single_event_detail)
    return event_details_list

def parse_events(url):
    events = []
    html_content = fetch_events(url)
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = soup.find_all('article', class_='blog-single-column--container')
    for article in articles:
        title_tag = article.find('h1', class_='blog-title').find('a')
        date_tag = article.find('time', class_='blog-date')
        if title_tag and date_tag:
            event_title = title_tag.text.strip()
            event_date_str = date_tag.text.strip()
            event_date = datetime.strptime(event_date_str, '%m/%d/%y')
            
            # Stop parsing if the event date is earlier than the cutoff date
            if event_date < CUTOFF_DATE:
                continue

            event_url = 'https://www.altovelo.org' + title_tag['href']
            events.append({
                'title': event_title,
                'date': event_date_str,
                'source_url': event_url
            })
    
    return events

def main():
    url = 'https://www.altovelo.org/c-ride'
    events_list = parse_events(url)
    event_details_list = parse_event_details(events_list)
    print(event_details_list)

if __name__ == '__main__':
    main()