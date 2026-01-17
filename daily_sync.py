# ==============================================================================
# GARMIN HEALTH SYNC ROBOT (V3 - SPLIT TOKEN FIX)
# ==============================================================================
import json
import os
import sys
import base64
import io
from datetime import date, datetime, timezone, timedelta
from garminconnect import Garmin
import garth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- HELPER: AUTOMATIC PADDING REPAIR ---
def repair_and_decode(base64_string):
    """
    Ensures the string is a multiple of 4 by adding '=' padding if needed.
    """
    base64_string = base64_string.strip()
    missing_padding = len(base64_string) % 4
    if missing_padding:
        base64_string += '=' * (4 - missing_padding)
    return base64.b64decode(base64_string)

# --- PRIVACY SCRUBBING ---
KEYS_TO_DELETE = ['sleepMovement', 'remSleepData', 'sleepLevels', 'deviceId', 'userProfilePk']
PRIVACY_TRIGGERS = ['lat', 'lon', 'location', 'address', 'city']

def scrub_data(data):
    if isinstance(data, dict):
        return {k: scrub_data(v) for k, v in data.items() 
                if k not in KEYS_TO_DELETE and not any(t in k.lower() for t in PRIVACY_TRIGGERS)}
    elif isinstance(data, list):
        return [scrub_data(item) for item in data]
    return data

# --- MAIN SYNC FUNCTION ---
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # 1. AUTHENTICATION: Glue the two parts together
        print("🔐 Authenticating with Garmin...")
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        full_token = p1 + p2
        
        if not full_token:
            print("❌ ERROR: GARMIN_PART1 or PART2 is missing from GitHub Secrets!")
            sys.exit(1)
            
        print(f"   -> Success: Assembled {len(full_token)} characters.")

        # 2. LOGIN: Use the repair helper to decode
        try:
            decoded_bytes = repair_and_decode(full_token)
            garth.client.loads(decoded_bytes.decode())
        except Exception as e:
            # This is where we catch if the string is still malformed
            print(f"❌ AUTH ERROR: The assembled token is invalid. Details: {e}")
            sys.exit(1)
        
        client = Garmin()
        client.garth = garth.client
        print("   -> Success: Logged into Garmin.\n")
        
        # 3. SETUP TIME (CST)
        CST = timezone(timedelta(hours=-6))
        today = datetime.now(CST).date().isoformat()
        timestamp = datetime.now(CST).strftime("%Y-%m-%d_%H-%M-%S")
        
        # 4. FETCH DATA
        print(f"📅 Fetching data for: {today}")
        data = {"timestamp": timestamp}
        try:
            data["sleep"] = client.get_sleep_data(today)
            print("   [+] Sleep data retrieved.")
        except: print("   [-] Sleep data not available.")

        # 5. UPLOAD TO DRIVE
        print("\n☁️ Uploading to Google Drive...")
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [os.environ["GDRIVE_FOLDER_ID"]]}
        clean_data = scrub_data(data)
        media = MediaIoBaseUpload(io.BytesIO(json.dumps(clean_data, indent=2).encode()), mimetype='application/json')
        
        file = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {file.get('id')}")

    except Exception as e:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
