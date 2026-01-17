# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V6 - SECURE SPLIT AUTH)
# This version uses secure GitHub Secrets and cleans invisible formatting bugs.
# ==============================================================================

import json         # For handling Google Drive credentials
import os           # For accessing secure GitHub Secrets
import sys          # For exiting the script if a problem occurs
import base64       # For decoding the Garmin session
import io           # For handling data in memory
import re           # For cleaning invisible characters from the token

# Time and Date tools
from datetime import date, datetime, timezone, timedelta

# Garmin & Google Drive tools
from garminconnect import Garmin
import garth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ------------------------------------------------------------------------------
# 1. CLEANING UTILITY
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    Removes every single character that is NOT a valid Base64 character.
    This kills invisible spaces and Word formatting tags.
    """
    # Keep only A-Z, a-z, 0-9, +, /, and =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Ensure the length is a multiple of 4 (Required for Base64 math)
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
    return cleaned

# ------------------------------------------------------------------------------
# 2. MAIN ROBOT LOGIC
# ------------------------------------------------------------------------------
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # STEP A: ASSEMBLE SECURE TOKEN
        # We glue the two halves back together to bypass the browser paste limit.
        print("🔐 Authenticating with Garmin...")
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        
        combined_raw = p1 + p2
        
        if not combined_raw:
            print("❌ ERROR: GARMIN_PART1 or PART2 is missing from Secrets!")
            sys.exit(1)
            
        # Clean the string of any hidden "ghost" characters
        clean_token = super_clean_base64(combined_raw)
        print(f"   -> Token assembled and cleaned. Length: {len(clean_token)} chars.")

        # STEP B: LOGIN TO GARMIN
        try:
            # Decode the text and load the session into the garth library
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: Invalid token. Details: {auth_err}")
            sys.exit(1)
        
        # STEP C: SETUP TIME (Central Standard Time)
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        # STEP D: FETCH DATA
        print(f"📅 Fetching health data for: {today_str}")
        health_data = {
            "timestamp": timestamp,
            "sleep": client.get_sleep_data(today_str),
            "body_battery": client.get_body_battery(today_str)
        }

        # STEP E: UPLOAD TO GOOGLE DRIVE
        print("\n☁️ Connecting to Google Drive...")
        
        # Pull Google Secrets from the GitHub vault
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        
        # Authenticate with Google
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare the file metadata and data stream
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(health_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        # Perform the upload
        uploaded = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {uploaded.get('id')}")

    except Exception as global_err:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {global_err}")
        sys.exit(1)

# Start the robot
if __name__ == "__main__":
    run_sync()
