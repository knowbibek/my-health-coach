# ==============================================================================
#  GARMIN -> GOOGLE DRIVE SYNC (CLEAN DATA + CST TIME + TIMESTAMPED FILE)
# ==============================================================================
#  VERSION: FINAL_CLEAN_V3
#  1. AUTH: Combines 3 secrets to log in.
#  2. CLEAN: Deletes huge arrays (Movement, SpO2) -> Keeps only summary numbers.
#  3. TIME: Forces CST (UTC-6) and adds time to the filename.
# ==============================================================================

import json
import os
import sys
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# --- Libraries ---
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
#  1. HELPER: CLEAN SECRETS
# ==============================================================================
def clean_token(raw_string):
    """Fixes formatting issues (spaces/newlines) in the secret token."""
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

# ==============================================================================
#  2. THE FILTER (REMOVES "LONG" DATA)
# ==============================================================================
def simplify_data(raw_sleep, raw_bb):
    """
    Takes the RAW massive data and extracts ONLY the summary numbers.
    This guarantees the output file is tiny (approx 20-30 lines).
    """
    # --- Sleep Summary ---
    # We navigate the complicated Garmin structure to find just the scores
    sleep_dto = raw_sleep.get('dailySleepDTO', {})
    scores = sleep_dto.get('sleepScores', {})
    
    # Calculate duration (Seconds -> Hours & Minutes)
    total_sec = sleep_dto.get('sleepTimeSeconds', 0)
    hours = int(total_sec // 3600)
    mins = int((total_sec % 3600) // 60)

    clean_sleep = {
        "date": sleep_dto.get('calendarDate'),
        "duration": f"{hours}h {mins}m",
        "score": scores.get('overall', {}).get('value'),
        "quality": scores.get('overall', {}).get('qualifierKey'),
        "deep_sleep_min": int(sleep_dto.get('deepSleepSeconds', 0) // 60),
        "rem_sleep_min": int(sleep_dto.get('remSleepSeconds', 0) // 60),
        "awake_count": sleep_dto.get('awakeCount'),
        "avg_stress": sleep_dto.get('avgSleepStress'),
        "avg_hrv": raw_sleep.get('sleepData', {}).get('avgOvernightHrv'),
        "resting_hr": sleep_dto.get('restingHeartRate')
    }

    # --- Body Battery Summary ---
    # Garmin gives a list of days. We grab only the first one (today).
    clean_bb = {"status": "No data"}
    
    if isinstance(raw_bb, list) and len(raw_bb) > 0:
        day_data = raw_bb[0]
        # The 'values' array is a graph. We grab the LAST point for current level.
        graph = day_data.get('bodyBatteryValuesArray', [])
        current_val = graph[-1][1] if graph else "N/A"
        
        clean_bb = {
            "current_level": current_val,
            "high": day_data.get('charged'),
            "low": day_data.get('drained')
        }

    return {
        "sleep": clean_sleep,
        "body_battery": clean_bb
    }

# ==============================================================================
#  3. MAIN SCRIPT
# ==============================================================================
def run_sync():
    print(f"\n{'='*40}\n   🚀 STARTING SYNC (VERSION: CLEAN_V3)\n{'='*40}\n")
    
    try:
        # --- PHASE 1: LOGIN ---
        print("🔐 Authenticating...")
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        
        token = clean_token(p1 + p2 + p3)
        if len(token) < 100:
            print("❌ Error: Secrets are empty or missing.")
            sys.exit(1)

        garth.client.loads(base64.b64decode(token).decode())
        client = Garmin()
        client.garth = garth.client
        print("   ✅ Logged in to Garmin.")

        # --- PHASE 2: TIMEZONE (CST) ---
        # CST is UTC-6
        CST = timezone(timedelta(hours=-6))
        now_cst = datetime.now(CST)
        
        # Create timestamps for filename and data
        date_str = now_cst.date().isoformat()      # 2026-01-17
        time_str = now_cst.strftime("%H-%M-%S")    # 16-30-05
        
        print(f"📅 Date: {date_str}")
        print(f"🕒 Time: {time_str} (CST)")

        # --- PHASE 3: FETCH & CLEAN ---
        print("\n🧹 Fetching and Cleaning Data...")
        raw_sleep = client.get_sleep_data(date_str)
        raw_bb = client.get_body_battery(date_str)
        
        # Apply the filter function
        final_data = {
            "timestamp_cst": f"{date_str}_{time_str}",
            "metrics": simplify_data(raw_sleep, raw_bb)
        }
        
        # Log the preview to verify it's short
        print(json.dumps(final_data, indent=2))

        # --- PHASE 4: UPLOAD ---
        print("\n☁️ Uploading to Drive...")
        oauth_json = os.environ.get("GDRIVE_OAUTH_JSON")
        folder_id = os.environ.get("GDRIVE_FOLDER_ID")
        
        creds = Credentials.from_authorized_user_info(json.loads(oauth_json))
        service = build('drive', 'v3', credentials=creds)
        
        # FILE NAME FORMAT: health_YYYY-MM-DD_HH-MM-SS.json
        filename = f"health_{date_str}_{time_str}.json"
        
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(final_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        service.files().create(
            body={'name': filename, 'parents': [folder_id]}, 
            media_body=media
        ).execute()
        
        print(f"✅ Success! File saved: {filename}")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
