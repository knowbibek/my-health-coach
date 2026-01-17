# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V4 - AGGRESSIVE CLEANING)
# This script handles the assembly of split tokens and cleans invisible bugs.
# ==============================================================================

import json         # For parsing Google Drive credentials
import os           # For accessing GitHub Secrets (Environment Variables)
import sys          # For exiting the script if a critical error occurs
import base64       # For decoding your Garmin session token
import io           # For handling the data file in memory before upload
import re           # For "Regex" - used to kill invisible formatting characters

# Time and Date libraries
from datetime import date, datetime, timezone, timedelta #

# Garmin & Google Drive libraries
from garminconnect import Garmin #
import garth #
from google.oauth2.service_account import Credentials #
from googleapiclient.discovery import build #
from googleapiclient.http import MediaIoBaseUpload #

# ------------------------------------------------------------------------------
# 1. THE "GHOST BUG" KILLER (CRITICAL FIX)
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    This function removes every single character that is NOT a valid Base64 
    character (A-Z, 0-9, etc.). It deletes invisible spaces and Word tags.
    """
    # Use Regex to keep ONLY valid Base64 characters: A-Z, a-z, 0-9, +, /, and =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Ensure the length is a multiple of 4 (Required for Base64 math)
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
    
    return cleaned

# ------------------------------------------------------------------------------
# 2. PRIVACY SCRUBBING
# ------------------------------------------------------------------------------
def scrub_data(data):
    """
    Removes technical IDs and location data so your personal info stays private.
    """
    # These fields are removed to save space and protect privacy
    KEYS_TO_REMOVE = ['deviceId', 'userProfilePk', 'sleepMovement', 'remSleepData']
    
    if isinstance(data, dict):
        return {k: scrub_data(v) for k, v in data.items() if k not in KEYS_TO_REMOVE}
    elif isinstance(data, list):
        return [scrub_data(item) for item in data]
    return data

# ------------------------------------------------------------------------------
# 3. MAIN ROBOT EXECUTION
# ------------------------------------------------------------------------------
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # STEP A: GATHER THE SECRETS
        print("🔐 Authenticating with Garmin...")
        p1 = os.environ.get("GARMIN_PART1", "") #
        p2 = os.environ.get("GARMIN_PART2", "") #
        
        # Combine the two halves you put in GitHub
        raw_combined = p1 + p2
        
        # CLEAN THE TOKEN: Remove invisible bugs introduced by copy-pasting
        clean_token = super_clean_base64(raw_combined)
        
        print(f"   -> Raw String: {len(raw_combined)} characters.")
        print(f"   -> Cleaned String: {len(clean_token)} characters.")

        # STEP B: LOGIN TO GARMIN
        try:
            # Decode the clean string into a Garmin session
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            
            # Start the client
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: The token is still invalid. Details: {auth_err}")
            sys.exit(1)
        
        # STEP C: SETUP TIME (Central Standard Time)
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        # STEP D: FETCH DATA
        print(f"📅 Fetching health data for: {today_str}")
        data_to_save = {
            "timestamp": timestamp,
            "sleep": client.get_sleep_data(today_str),
            "body_battery": client.get_body_battery(today_str)
        }

        # STEP E: UPLOAD TO GOOGLE DRIVE
        print("\n☁️ Connecting to Google Drive...")
        
        # Load Google Credentials
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare the file for upload
        clean_payload = scrub_data(data_to_save)
        file_stream = io.BytesIO(json.dumps(clean_payload, indent=2).encode())
        media = MediaIoBaseUpload(file_stream, mimetype='application/json')
        
        # Execute the upload to your specific folder
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [folder_id]}
        
        uploaded_file = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {uploaded_file.get('id')}")

    except Exception as global_error:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {global_error}")
        sys.exit(1)

# Start the robot
if __name__ == "__main__":
    run_sync()
