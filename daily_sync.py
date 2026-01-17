# ==============================================================================
#  GARMIN -> GOOGLE DRIVE SYNC (PRIVACY & AI OPTIMIZED)
#  ----------------------------------------------------------------------------
#  Features:
#    1. 100% Privacy: Removes Device IDs, User IDs, and Location data.
#    2. AI-Ready: Formats data specifically for LLMs/Dashboards.
#    3. Clean Drive: Overwrites 'health_latest.json' to prevent clutter.
# ==============================================================================

import json, os, sys, base64, io, re
from datetime import datetime, timezone, timedelta
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

def super_clean_base64(raw_string):
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    while len(cleaned) % 4 != 0: cleaned += '='
    return cleaned

def filter_for_privacy(raw_sleep, raw_bb):
    """
    Strictly filters data to remove IDs, location, and noise.
    Keeps only high-level health metrics useful for AI analysis.
    """
    # 1. SLEEP METRICS
    sleep_dto = raw_sleep.get('dailySleepDTO', {})
    scores = sleep_dto.get('sleepScores', {})
    
    clean_sleep = {
        "summary": "Last night's sleep data",
        "duration_hours": round(sleep_dto.get('sleepTimeSeconds', 0) / 3600, 2),
        "sleep_score": scores.get('overall', {}).get('value'),
        "sleep_quality": scores.get('overall', {}).get('qualifierKey'),
        "deep_sleep_hours": round(sleep_dto.get('deepSleepSeconds', 0) / 3600, 2),
        "rem_sleep_hours": round(sleep_dto.get('remSleepSeconds', 0) / 3600, 2),
        "awake_minutes": round(sleep_dto.get('awakeSleepSeconds', 0) / 60, 0),
        "avg_stress_during_sleep": sleep_dto.get('avgSleepStress'),
        "hrv_status": raw_sleep.get('sleepData', {}).get('hrvStatus'),
        "avg_hrv_value": raw_sleep.get('sleepData', {}).get('avgOvernightHrv')
    }

    # 2. BODY BATTERY METRICS
    # Get the most recent value from the list
    bb_list = raw_bb if isinstance(raw_body_battery, list) else []
    current_bb = "Unknown"
    
    if bb_list and 'bodyBatteryValuesArray' in bb_list[0]:
        # Get the very last recorded value (most current)
        values = bb_list[0]['bodyBatteryValuesArray']
        if values:
            current_bb = values[-1][1]  # The last value in the list

    clean_bb = {
        "summary": "Energy levels for the day",
        "current_level": current_bb,
        "charged_today": bb_list[0].get('charged') if bb_list else 0,
        "drained_today": bb_list[0].get('drained') if bb_list else 0,
    }

    return {"sleep": clean_sleep, "body_battery": clean_bb}

def run_sync():
    print(f"\n{'='*40}\n   🛡️ PRIVACY-FIRST HEALTH SYNC\n{'='*40}\n")
    
    try:
        # --- PHASE 1: AUTHENTICATION ---
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        full_token = super_clean_base64(p1 + p2 + p3)
        
        if len(full_token) < 100: sys.exit("❌ Secrets missing.")

        decoded_bytes = base64.b64decode(full_token)
        garth.client.loads(decoded_bytes.decode())
        client = Garmin()
        client.garth = garth.client
        print("   ✅ Authenticated (Garmin)")

        # --- PHASE 2: FETCH & SANITIZE ---
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        
        raw_sleep = client.get_sleep_data(today_str)
        raw_bb = client.get_body_battery(today_str)
        
        final_data = {
            "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": today_str,
            "metrics": filter_for_privacy(raw_sleep, raw_bb)
        }
        
        print(f"   ✅ Data Sanitized (IDs/Location Removed)")

        # --- PHASE 3: UPLOAD (OVERWRITE MODE) ---
        oauth_json = os.environ.get("GDRIVE_OAUTH_JSON")
        folder_id = os.environ.get("GDRIVE_FOLDER_ID")
        
        creds = Credentials.from_authorized_user_info(json.loads(oauth_json))
        service = build('drive', 'v3', credentials=creds)
        
        # Check if file exists to overwrite it instead of creating duplicates
        query = f"name = 'health_latest.json' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        files = results.get('files', [])

        media_content = MediaIoBaseUpload(io.BytesIO(json.dumps(final_data, indent=2).encode()), mimetype='application/json')

        if files:
            # UPDATE existing file
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media_content).execute()
            print(f"   ✅ Updated existing file (ID: {file_id})")
        else:
            # CREATE new file
            file_metadata = {'name': 'health_latest.json', 'parents': [folder_id]}
            service.files().create(body=file_metadata, media_body=media_content).execute()
            print(f"   ✅ Created new file")

    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
