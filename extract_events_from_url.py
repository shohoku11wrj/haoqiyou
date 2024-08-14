import requests
from bs4 import BeautifulSoup

def extract_ride_event_details(url):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to retrieve the page: {response.status_code}")
        return None

    # print(response.content)

    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract event details (this will depend on the structure of the webpage)
    event_details = {}

    # Example: Extracting the event title
    title_title = soup.select_one('div.blog-item-wrapper div.blog-item-title h1.entry-title')
    if title_title:
        event_details['title'] = title_title.text.strip()
    else:
        event_details['title'] = ""

    # # Example: Extracting the event date
    # date_tag = soup.find('div', class_='event-date')
    # if date_tag:
    #     event_details['date'] = date_tag.text.strip()

    # # Example: Extracting the event description
    # description_tag = soup.find('div', class_='event-description')
    # if description_tag:
    #     event_details['description'] = description_tag.text.strip()

    # # Add more extraction logic as needed based on the webpage structure

    return event_details

# URL of the event page
event_url = 'https://www.altovelo.org/c-ride/av-c-ride-august-10th-2024-portola-state-park'
event_details = extract_ride_event_details(event_url)

if event_details:
    print("Event Details:")
    for key, value in event_details.items():
        print(f"{key}: {value}")
else:
    print("No event details found.")