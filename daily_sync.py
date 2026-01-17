# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V5 - FINAL FILE FIX)
# This script reads your login session from 'garmin_tokens.txt'.
# ==============================================================================

import json         # For handling Google Drive credentials
import os           # For accessing files and GitHub environment variables
import sys          # For stopping the script if an error occurs
import base64       # For decoding your Garmin login session
import io           # For handling data in memory before upload
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
    Strips out every single character that is NOT a valid Base64 character.
    This fixes issues caused by copying from browsers or Microsoft Word.
    """
    # Keep only A-Z, a-z, 0-9, +, /, and =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Ensure length is a multiple of 4 (Required for Base64)
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
    return cleaned

# ------------------------------------------------------------------------------
# 2. MAIN SYNC LOGIC
# ------------------------------------------------------------------------------
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # --- STEP A: LOAD TOKEN FROM THE REPOSITORY FILE ---
        print("🔐 Authenticating with Garmin...")
        token_filename = "garmin_tokens.txt"
        
        # Check if the file actually exists in the current folder
        if not os.path.exists(token_filename):
            print(f"❌ ERROR: Cannot find the file '{token_filename}'!")
            print(f"   Current files visible to robot: {os.listdir('.')}")
            sys.exit(1)
            
        with open(token_filename, "r") as file:
            raw_content = file.read()
            
        # Remove any accidental hidden spaces or formatting characters
        clean_token = super_clean_base64(raw_content)
        print(f"   -> Raw String: {len(raw_content)} characters.")
        print(f"   -> Cleaned String: {len(clean_token)} characters.")

        if len(clean_token) == 0:
            print("❌ ERROR: The 'garmin_tokens.txt' file appears to be empty!")
            sys.exit(1)

        # --- STEP B: LOGIN TO GARMIN ---
        try:
            # Decode the text and load the session into the 'garth' library
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: Decryption failed. Details: {auth_err}")
            sys.exit(1)
        
        # --- STEP C: FETCH DATA ---
        CST = timezone(timedelta(hours=-6))
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"📅 Fetching data for: {today_str}")
        health_data = {
            "timestamp": timestamp,
            "sleep": client.get_sleep_data(today_str),
            "body_battery": client.get_body_battery(today_str)
        }

        # --- STEP D: UPLOAD TO GOOGLE DRIVE ---
        print("\n☁️ Connecting to Google Drive...")
        creds_info = json.loads(os.environ["GDRIVE_JSON"])
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare the file
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(health_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        uploaded = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {uploaded.get('id')}")

    except Exception as global_err:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {global_err}")
        sys.exit(1)

# Start the robot!
if __name__ == "__main__":
    run_sync()
