import xml.etree.ElementTree as ET
import base64
import json
import glob
import os

def encode_polyline(coordinates, precision=5):
    """
    Encode a list of coordinates into a polyline string.
    
    :param coordinates: List of coordinate pairs (latitude, longitude)
    :param precision: Precision of encoding (default 5)
    :return: Encoded polyline string
    """
    factor = 10 ** precision
    encoded = ''
    prev_lat, prev_lng = 0, 0
    
    for lat, lng in coordinates:
        lat_diff = int(round(lat * factor)) - prev_lat
        lng_diff = int(round(lng * factor)) - prev_lng
        
        prev_lat = int(round(lat * factor))
        prev_lng = int(round(lng * factor))
        
        encoded += _encode_number(lat_diff) + _encode_number(lng_diff)
    
    return encoded

def _encode_number(num):
    """Helper function to encode a single number."""
    num = ~(num << 1) if num < 0 else num << 1
    encoded = ''
    while num >= 0x20:
        encoded += chr((0x20 | (num & 0x1f)) + 63)
        num >>= 5
    encoded += chr(num + 63)
    return encoded

def decode_polyline(polyline, precision=5):
    """
    Decode a polyline string into a list of coordinates.
    
    :param polyline: Encoded polyline string
    :param precision: Precision of decoding (default 5)
    :return: List of coordinate pairs (latitude, longitude)
    """
    factor = 10 ** precision
    coordinates = []
    index, lat, lng = 0, 0, 0
    
    while index < len(polyline):
        shift, result = 0, 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        
        lat_change = ~(result >> 1) if result & 1 else result >> 1
        lat += lat_change
        
        shift, result = 0, 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        
        lng_change = ~(result >> 1) if result & 1 else result >> 1
        lng += lng_change
        
        coordinates.append((lat / factor, lng / factor))
    
    return coordinates

# Example usage:
if __name__ == "__main__":
    # Example coordinates
    coords = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    
    # Encode
    encoded = encode_polyline(coords)
    print("Encoded polyline:", encoded)
    
    # Decode
    decoded = decode_polyline(encoded)
    print("Decoded coordinates:", decoded)
    
    # Verify
    print("Original coordinates match decoded:", coords == decoded)


def extract_gps_coordinates(gpx_file):
    tree = ET.parse(gpx_file)
    root = tree.getroot()
    
    # Define the namespace
    namespace = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    
    coordinates = []
    for trkpt in root.findall('.//gpx:trkpt', namespace):
        lat = float(trkpt.get('lat'))
        lon = float(trkpt.get('lon'))
        coordinates.append([lat, lon])
    
    return coordinates

def serialize_to_base64(data):
    json_str = json.dumps(data)
    return base64.b64encode(json_str.encode()).decode()

### MAIN FUNCTION ###
# Find the GPX file
gpx_files = glob.glob('./ignore_this/COURSE_*.gpx')
if not gpx_files:
    raise FileNotFoundError("No GPX file found in ./ignore_this/ directory")

gpx_file = gpx_files[0]  # Take the first file if multiple files exist

# Extract GPS coordinates
coordinates = extract_gps_coordinates(gpx_file)

# Serialize to base64
serialized_data = encode_polyline(coordinates)

print(serialized_data)
