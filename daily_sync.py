# ==============================================================================
#  GARMIN -> DRIVE SYNC (FINAL CLEAN VERSION)
# ==============================================================================
#  1. AUTHENTICATION: Logs in using your 3-part secret.
#  2. DATA DIET: Removes all long arrays (Movement, SpO2, Respiration).
#  3. TIMEZONE: Forces CST (UTC-6) for accurate daily tracking.
#  4. FILENAME: Saves as "health_YYYY-MM-DD_HH-MM-SS.json"
# ==============================================================================

import json
import os
import sys
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# --- Third-Party Libraries ---
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
#  HELPER 1: CLEAN SECRETS
# ==============================================================================
def clean_base64(raw_string):
    """
    Removes invisible characters (spaces, newlines) from the secrets
    and fixes the padding so the computer can read them.
    """
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

# ==============================================================================
#  HELPER 2: THE "DATA DIET" (Strict Filter)
# ==============================================================================
def get_clean_summary(raw_sleep, raw_bb):
    """
    Takes the massive raw data and extracts ONLY specific numbers.
    It returns a small dictionary, guaranteeing no 'noise' gets through.
    """
    # --- A. SLEEP SUMMARY ---
    # We use .get() to safely grab data without crashing if something is missing
    dto = raw_sleep.get('dailySleepDTO', {})
    scores = dto.get('sleepScores', {})
    
    # Convert Total Seconds -> "X hrs Y mins"
    total_sec = dto.get('sleepTimeSeconds', 0)
    hrs = int(total_sec // 3600)
    mins = int((total_sec % 3600) // 60)

    clean_sleep = {
        "date": dto.get('calendarDate'),
        "duration": f"{hrs}h {mins}m",
        "score": scores.get('overall', {}).get('value'),
        "quality": scores.get('overall', {}).get('qualifierKey'),  # e.g. "GOOD"
        "deep_sleep_min": int(dto.get('deepSleepSeconds', 0) // 60),
        "rem_sleep_min": int(dto.get('remSleepSeconds', 0) // 60),
        "awake_count": dto.get('awakeCount'),
        "avg_stress": dto.get('avgSleepStress'),
        "avg_hrv": raw_sleep.get('sleepData', {}).get('avgOvernightHrv'),
        "resting_hr": dto.get('restingHeartRate')
    }

    # --- B. BODY BATTERY ---
    # Garmin returns a list of days; we want the first one (Today)
    clean_bb = {"status": "No Data"}
    
    if isinstance(raw_bb, list) and len(raw_bb) > 0:
        day_data = raw_bb[0]
        # The 'values' array is a graph [time, value]. We grab the LAST one.
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
#  MAIN SCRIPT
# ==============================================================================
def run_sync():
    print(f"\n{'='*40}\n   🚀 STARTING SYNC (CLEAN MODE)\n{'='*40}\n")
    
    try:
        # --- PHASE 1: LOGIN ---
        print("🔐 [1/4] Authenticating...")
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        
        token = clean_base64(p1 + p2 + p3)
        if len(token) < 100:
            print("❌ Error: Secrets are missing.")
            sys.exit(1)

        garth.client.loads(base64.b64decode(token).decode())
        client = Garmin()
        client.garth = garth.client
        print("   ✅ Logged in.")

        # [START NEW CODE] --------------------------------------------
        # We need your User ID to get the 'Deep Dive' data safely.
        print("🕵️ Identifying User...")
        profile = garth.client.connectapi("/userprofile-service/socialProfile")
        if isinstance(profile, list): profile = profile[0]
        display_name = profile.get("displayName")
        print(f"   ✅ User ID Found: {display_name}")
        # [END NEW CODE] ----------------------------------------------

        # --- PHASE 2: TIMEZONE (CST) ---
        # Force Central Standard Time (UTC-6)
        CST = timezone(timedelta(hours=-6))
        now_cst = datetime.now(CST)
        
        date_str = now_cst.date().isoformat()       # 2026-01-17
        time_str = now_cst.strftime("%H-%M-%S")     # 16-30-00
        
        print(f"\n📅 [2/4] Fetching Data for: {date_str} (CST Time: {time_str})")

        # --- PHASE 3: FETCH & CLEAN ---
        raw_sleep = client.get_sleep_data(date_str)
        raw_bb = client.get_body_battery(date_str)
       # [START NEW CODE] --------------------------------------------
        # This grabs the 86 variables (Stress, Calories) safely
        deep_summary = {}
        try:
            url = f"/usersummary-service/usersummary/daily/{display_name}?calendarDate={date_str}"
            deep_data = garth.client.connectapi(url)
            if isinstance(deep_data, list) and deep_data: deep_data = deep_data[0]
            deep_summary = deep_data
            print(f"   ✅ Deep Dive: Captured {len(deep_summary.keys())} extra variables.")
        except Exception as e:
            print(f"   ⚠️ Deep Dive Warning: {e}")
        # [END NEW CODE] ----------------------------------------------
        
        # *** THE IMPORTANT PART: Filtering ***
        # [UPDATED CODE] ----------------------------------------------
        final_payload = {
            "timestamp_cst": f"{date_str}_{time_str}",
            "metrics": get_clean_summary(raw_sleep, raw_bb), # Your trusted clean data
            "deep_dive": deep_summary                        # The new extra intel
        }
        # [END UPDATED CODE] ------------------------------------------
        
        # Show preview in logs to verify it is SHORT
        print("\n🔍 PREVIEW (This is what Gem will see):")
        print(json.dumps(final_payload, indent=2))

        # --- PHASE 4: UPLOAD ---
        print("\n☁️  [3/4] Uploading to Drive...")
        
        oauth_json = os.environ.get("GDRIVE_OAUTH_JSON")
        folder_id = os.environ.get("GDRIVE_FOLDER_ID")
        
        creds = Credentials.from_authorized_user_info(json.loads(oauth_json))
        service = build('drive', 'v3', credentials=creds)
        
        # FILENAME: health_YYYY-MM-DD_HH-MM-SS.json
        filename = f"health_{date_str}_{time_str}.json"
        
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(final_payload, indent=2).encode()), 
            mimetype='application/json'
        )
        
        service.files().create(
            body={'name': filename, 'parents': [folder_id]}, 
            media_body=media
        ).execute()
        
        print(f"   ✅ Upload Complete!")
        print(f"   📄 Saved as: {filename}")
        print(f"\n{'='*40}\n   🎉 SUCCESS \n{'='*40}\n")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
