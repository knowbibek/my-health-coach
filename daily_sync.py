# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V10 - TRIPLE CHUNK FIX)
# This script re-assembles the split token, cleans it, and syncs your data.
# ==============================================================================

import json         # For handling Google Drive credentials
import os           # For accessing the 3 secret parts from the environment
import sys          # For safely stopping the script if errors occur
import base64       # For decoding the re-assembled Garmin token
import io           # For handling the data stream in memory
import re           # For "Regex" cleaning of invisible characters

# Time and Date libraries
from datetime import date, datetime, timezone, timedelta

# Garmin & Google Drive libraries
from garminconnect import Garmin
import garth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ------------------------------------------------------------------------------
# 1. CLEANING UTILITY: THE "GHOST BUG" FIXER
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    Takes the raw text and removes any character that isn't valid Base64 code.
    This fixes issues where copying from a browser adds invisible spaces.
    """
    # Rule 1: Remove anything that is NOT A-Z, a-z, 0-9, +, /, or =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Rule 2: Ensure the length is a multiple of 4 (Required for Base64 math)
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

# ------------------------------------------------------------------------------
# 2. MAIN SYNC LOGIC
# ------------------------------------------------------------------------------
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # --- PHASE 1: TOKEN ASSEMBLY ---
        print("🔐 Authenticating with Garmin...")
        
        # Fetch the 3 parts from GitHub Secrets
        p1 = os.environ.get("GARMIN_PART1", "")
        p2 = os.environ.get("GARMIN_PART2", "")
        p3 = os.environ.get("GARMIN_PART3", "")
        
        # Verify we actually have data
        if not p1:
            print("❌ ERROR: Secrets are missing! Please check GARMIN_PART1 in Settings.")
            sys.exit(1)

        # Stitch the parts back together into one long string
        full_raw_token = p1 + p2 + p3
        
        # Clean the stitched string to remove any 'ghost' formatting characters
        clean_token = super_clean_base64(full_raw_token)
        
        # Print stats so we can verify the fix in the logs
        print(f"   -> Part 1 Length: {len(p1)} chars")
        print(f"   -> Part 2 Length: {len(p2)} chars")
        print(f"   -> Part 3 Length: {len(p3)} chars")
        print(f"   -> TOTAL Assembled: {len(full_raw_token)} chars")
        print(f"   -> Final Cleaned:   {len(clean_token)} chars")

        # --- PHASE 2: LOGIN ---
        try:
            # Decode the clean string back into a session object
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            
            # Initialize the Garmin client with this session
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: The token is invalid. Details: {auth_err}")
            sys.exit(1)
        
        # --- PHASE 3: FETCH DATA (Central Standard Time) ---
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"📅 Fetching health data for: {today_str}")
        health_data = {
            "timestamp": timestamp,
            "sleep": client.get_sleep_data(today_str),
            "body_battery": client.get_body_battery(today_str)
        }

        # --- PHASE 4: UPLOAD TO GOOGLE DRIVE ---
        print("\n☁️ Connecting to Google Drive...")
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        
        # Authenticate with Google
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare the file in memory
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(health_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        # Send it to the cloud
        uploaded = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {uploaded.get('id')}")

    except Exception as global_err:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {global_err}")
        sys.exit(1)

# Start the robot
if __name__ == "__main__":
    run_sync()
