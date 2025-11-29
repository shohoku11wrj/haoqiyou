import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EVENTS_JSON_PATH = BASE_DIR / "storage" / "events.json"
EVENTS_JS_PATH = BASE_DIR / "storage" / "events.js"

# To refresh local events.js, run this script:
# python generate_local_data.py
def main():
    if not EVENTS_JSON_PATH.exists():
        print(f"Error: {EVENTS_JSON_PATH} not found.")
        return

    try:
        with open(EVENTS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        js_content = f"window.LOCAL_EVENTS_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};"
        
        with open(EVENTS_JS_PATH, "w", encoding="utf-8") as f:
            f.write(js_content)
            
        print(f"Successfully generated {EVENTS_JS_PATH}")
    except Exception as e:
        print(f"Error generating events.js: {e}")

if __name__ == "__main__":
    main()
