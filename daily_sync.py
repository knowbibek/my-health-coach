# ==============================================================================
#  GARMIN -> GOOGLE DRIVE SYNC ROBOT (USER MODE)
#  ----------------------------------------------------------------------------
#  Purpose: 
#    1. Authenticates with Garmin using a "Triple-Chunk" token to bypass limits.
#    2. Fetches your daily health metrics (Sleep, Body Battery).
#    3. Authenticates with Google Drive using your Personal OAuth Key (User Mode).
#    4. Uploads the data to your specific folder without using robot storage quota.
# ==============================================================================

import json
import os
import sys
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# --- Third Party Libraries ---
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ------------------------------------------------------------------------------
#  HELPER UTILITIES
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    Cleans a Base64 string by removing invisible characters (newlines, spaces)
    and ensures the length is a multiple of 4 by adding '=' padding.
    """
    # Remove anything that isn't a valid Base64 character
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Fix padding (Base64 requires length to be divisible by 4)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned


# ------------------------------------------------------------------------------
#  MAIN LOGIC
# ------------------------------------------------------------------------------
def run_sync():
    print(f"\n{'='*40}\n   🚀 STARTING HEALTH SYNC ROBOT\n{'='*40}\n")
    
    try:
        # ======================================================================
        # PHASE 1: GARMIN AUTHENTICATION
        # ======================================================================
        print("🔒 [1/3] Authenticating with Garmin...")
        
        # 1a. Retrieve the Token Parts from GitHub Secrets
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        
        # 1b. Assemble and Clean the Token
        full_token = super_clean_base64(p1 + p2 + p3)
        
        if len(full_token) < 100:
             print("   ❌ ERROR: Garmin secrets appear to be missing or empty.")
             sys.exit(1)

        # 1c. Log in using the 'garth' library
        try:
            decoded_bytes = base64.b64decode(full_token)
            garth.client.loads(decoded_bytes.decode())
            
            client = Garmin()
            client.garth = garth.client
            print("   ✅ Success: Connected to Garmin Connect.")
            
        except Exception as e:
            print(f"   ❌ AUTH FAILED: Could not log in to Garmin. Details: {e}")
            sys.exit(1)
        
        # ======================================================================
        # PHASE 2: FETCH HEALTH DATA
        # ======================================================================
        # Calculate 'Today' in your Timezone (Central Standard Time)
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"\n📥 [2/3] Fetching Data for: {today_str}")
        
        # 2a. Download the Metrics
        try:
            health_data = {
                "timestamp": timestamp,
                "date": today_str,
                "sleep_data": client.get_sleep_data(today_str),
                "body_battery": client.get_body_battery(today_str)
            }
            print(f"   ✅ Data collected successfully.")
        except Exception as e:
            print(f"   ❌ DATA ERROR: Could not fetch stats from Garmin. {e}")
            sys.exit(1)

        # ======================================================================
        # PHASE 3: GOOGLE DRIVE UPLOAD (USER MODE)
        # ======================================================================
        print("\n☁️  [3/3] Uploading to Google Drive...")
        
        # 3a. Retrieve the Personal OAuth Key
        oauth_json = os.environ.get("GDRIVE_OAUTH_JSON")
        folder_id = os.environ.get("GDRIVE_FOLDER_ID")

        if not oauth_json:
            print("   ❌ ERROR: Missing 'GDRIVE_OAUTH_JSON' secret.")
            sys.exit(1)
            
        # 3b. Authenticate as YOU (The User)
        creds = Credentials.from_authorized_user_info(json.loads(oauth_json))
        service = build('drive', 'v3', credentials=creds)
        
        # 3c. Prepare the JSON File for Upload
        file_metadata = {
            'name': f"health_{today_str}.json", 
            'parents': [folder_id]
        }
        
        media_content = MediaIoBaseUpload(
            io.BytesIO(json.dumps(health_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        # 3d. Send to Cloud
        uploaded_file = service.files().create(
            body=file_metadata, 
            media_body=media_content
        ).execute()
        
        print(f"   ✅ UPLOAD COMPLETE!")
        print(f"   📄 File ID: {uploaded_file.get('id')}")
        print(f"\n{'='*40}\n   🎉 MISSION ACCOMPLISHED \n{'='*40}\n")

    except Exception as global_error:
        print(f"\n💥 CRITICAL SYSTEM ERROR: {global_error}")
        sys.exit(1)

# --- ENTRY POINT ---
if __name__ == "__main__":
    run_sync()
