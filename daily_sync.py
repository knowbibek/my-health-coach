# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V9 - SINGLE TOKEN EDITION)
# This script uses one single Secret to authenticate with Garmin.
# ==============================================================================

import json, os, sys, base64, io, re
from datetime import date, datetime, timezone, timedelta
from garminconnect import Garmin
import garth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ------------------------------------------------------------------------------
# 1. THE "GHOST BUG" CLEANER
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    Removes invisible characters and fixes 'Multiple of 4' math errors.
    """
    # Keep only A-Z, 0-9, +, /, and =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Ensure the length is a multiple of 4 (Required for Base64)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

# ------------------------------------------------------------------------------
# 2. MAIN SYNC LOGIC
# ------------------------------------------------------------------------------
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # STEP A: LOAD THE SINGLE TOKEN
        print("🔐 Authenticating with Garmin...")
        raw_token = os.environ.get("GARMIN_TOKEN", "")
        
        # Aggressively clean the input
        clean_token = super_clean_base64(raw_token)
        
        print(f"   -> Raw String Received: {len(raw_token)} chars.")
        print(f"   -> Cleaned Token: {len(clean_token)} chars.")

        if len(clean_token) < 100:
            print("❌ ERROR: GARMIN_TOKEN is too short or missing!")
            sys.exit(1)

        # STEP B: LOGIN TO GARMIN
        try:
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: Authentication failed. Details: {auth_err}")
            sys.exit(1)
        
        # STEP C: FETCH AND UPLOAD DATA
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"📅 Fetching data for: {now.date().isoformat()}")
        data = {"timestamp": timestamp, "sleep": client.get_sleep_data(now.date().isoformat())}

        print("☁️ Uploading to Drive...")
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        service = build('drive', 'v3', credentials=Credentials.from_service_account_info(creds_info))
        
        file_meta = {'name': f"health_{timestamp}.json", 'parents': [os.environ["GDRIVE_FOLDER_ID"]]}
        media = MediaIoBaseUpload(io.BytesIO(json.dumps(data, indent=2).encode()), mimetype='application/json')
        
        service.files().create(body=file_meta, media_body=media).execute()
        print("✅ MISSION COMPLETE")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
