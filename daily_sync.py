# ==============================================================================
#  HEALTH SYNC ROBOT (Clean, Private, CST Timezone)
#  ----------------------------------------------------------------------------
#  1. Authenticates with Garmin (using 3-part secret)
#  2. Fetches raw data and aggressively filters out "noise" (privacy focused)
#  3. Saves a timestamped summary file to Google Drive
# ==============================================================================

import json
import os
import sys
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# --- External Libraries ---
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
#  SECTION 1: HELPER FUNCTIONS
# ==============================================================================

def super_clean_base64(raw_string):
    """
    Cleans the secret token strings.
    Removes invisible spaces/newlines and fixes padding for Base64 math.
    """
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

def simplify_health_data(raw_sleep, raw_bb):
    """
    THE DATA DIET:
    Takes massive raw data and returns a tiny, clean summary.
    Removes all sensitive IDs, location data, and minute-by-minute noise.
    """
    # --- 1. Process Sleep Data ---
    # We use .get() to safely grab data, returning None if missing
    sleep_dto = raw_sleep.get('dailySleepDTO', {})
    scores = sleep_dto.get('sleepScores', {})
    
    # Convert seconds to readable "Hours + Minutes" string
    duration_sec = sleep_dto.get('sleepTimeSeconds', 0)
    hours = int(duration_sec // 3600)
    minutes = int((duration_sec % 3600) // 60)

    clean_sleep = {
        "date": sleep_dto.get('calendarDate'),
        "total_duration": f"{hours}h {minutes}m",
        "score": scores.get('overall', {}).get('value'),
        "quality": scores.get('overall', {}).get('qualifierKey'), # e.g. "POOR", "GOOD"
        "deep_sleep_mins": int(sleep_dto.get('deepSleepSeconds', 0) // 60),
        "rem_sleep_mins": int(sleep_dto.get('remSleepSeconds', 0) // 60),
        "awake_count": sleep_dto.get('awakeCount'),
        "avg_stress": sleep_dto.get('avgSleepStress'),
        "avg_hrv": raw_sleep.get('sleepData', {}).get('avgOvernightHrv'),
        "resting_hr": sleep_dto.get('restingHeartRate')
    }

    # --- 2. Process Body Battery ---
    # Garmin returns a list; we usually just want the first entry (today)
    bb_list = raw_bb if isinstance(raw_bb, list) else []
    clean_bb = {"status": "No data available"}
    
    if bb_list:
        day_data = bb_list[0]
        # Access the graph array to find the *current* (last) value
        graph = day_data.get('bodyBatteryValuesArray', [])
        current_val = graph[-1][1] if graph else None
        
        clean_bb = {
            "current_level": current_val,
            "highest_charged": day_data.get('charged'),
            "lowest_drained": day_data.get('drained'),
        }

    # Combine nicely
    return {
        "sleep_summary": clean_sleep,
        "body_battery": clean_bb
    }

# ==============================================================================
#  SECTION 2: MAIN EXECUTION
# ==============================================================================

def run_sync():
    print(f"\n{'='*40}\n   🚀 STARTING SYNC ROBOT\n{'='*40}\n")
    
    try:
        # ----------------------------------------------------------------------
        # PHASE A: AUTHENTICATION
        # ----------------------------------------------------------------------
        print("🔐 [1/4] Authenticating with Garmin...")
        
        # 1. combine the 3 secret parts
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        
        full_token = super_clean_base64(p1 + p2 + p3)
        
        if len(full_token) < 100:
            print("❌ Error: Garmin secrets are missing or too short.")
            sys.exit(1)

        # 2. Login
        garth.client.loads(base64.b64decode(full_token).decode())
        client = Garmin()
        client.garth = garth.client
        print("   ✅ Success: Logged in.")

        # ----------------------------------------------------------------------
        # PHASE B: TIMEZONE SETUP (CST)
        # ----------------------------------------------------------------------
        # Force Central Standard Time (UTC-6)
        CST = timezone(timedelta(hours=-6))
        now_cst = datetime.now(CST)
        
        date_str = now_cst.date().isoformat()      # Format: 2026-01-17
        time_str = now_cst.strftime("%H-%M-%S")    # Format: 16-30-00
        
        print(f"\n📅 [2/4] Fetching data for: {date_str} (Time: {time_str} CST)")

        # ----------------------------------------------------------------------
        # PHASE C: FETCH & CLEAN DATA
        # ----------------------------------------------------------------------
        raw_sleep = client.get_sleep_data(date_str)
        raw_bb = client.get_body_battery(date_str)
        
        # Run the "Data Diet" function
        final_payload = {
            "timestamp_cst": f"{date_str}_{time_str}",
            "data": simplify_health_data(raw_sleep, raw_bb)
        }
        
        # Show a preview in the logs (helpful for debugging)
        print("\n🔍 PREVIEW (Clean Data for Gem):")
        print(json.dumps(final_payload, indent=2))

        # ----------------------------------------------------------------------
        # PHASE D: UPLOAD TO GOOGLE DRIVE
        # ----------------------------------------------------------------------
        print("\n☁️  [3/4] Uploading to Google Drive...")
        
        oauth_json = os.environ.get("GDRIVE_OAUTH_JSON")
        folder_id = os.environ.get("GDRIVE_FOLDER_ID")
        
        # Login to Drive acting as YOU (User Mode)
        creds = Credentials.from_authorized_user_info(json.loads(oauth_json))
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare file metadata with timestamped name
        filename = f"health_{date_str}_{time_str}.json"
        
        file_metadata = {
            'name': filename, 
            'parents': [folder_id]
        }
        
        # Prepare the file content
        media_content = MediaIoBaseUpload(
            io.BytesIO(json.dumps(final_payload, indent=2).encode()), 
            mimetype='application/json'
        )
        
        # Create the new file
        uploaded_file = service.files().create(
            body=file_metadata, 
            media_body=media_content
        ).execute()
        
        print(f"   ✅ Upload Complete!")
        print(f"   📄 Saved as: {filename}")
        print(f"\n{'='*40}\n   🎉 MISSION ACCOMPLISHED \n{'='*40}\n")

    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
