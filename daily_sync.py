# ==============================================================================
# GARMIN -> GOOGLE DRIVE SYNC ROBOT (V6 - ROBUST FILE READ)
# This script reads your login session from 'garmin_tokens.txt' and 
# uploads your health data to Google Drive as a JSON file.
# ==============================================================================

import json         # For handling Google Drive credentials
import os           # For absolute path resolution and environment variables
import sys          # For graceful exits on critical errors
import base64       # For decoding the Garmin session token
import io           # For handling the data stream in memory
import re           # For cleaning invisible characters from the token file

# Time and Date libraries
from datetime import date, datetime, timezone, timedelta

# Garmin & Google Drive libraries
from garminconnect import Garmin
import garth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ------------------------------------------------------------------------------
# 1. CLEANING UTILITY: KILL INVISIBLE BUGS
# ------------------------------------------------------------------------------
def super_clean_base64(raw_string):
    """
    Removes every single character that is NOT a valid Base64 character.
    This fixes issues caused by hidden tags from browser copy-pasting.
    """
    # Keep only A-Z, a-z, 0-9, +, /, and =
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Ensure the string length is a multiple of 4 (Required for Base64)
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
        # --- STEP A: LOAD TOKEN FROM REPOSITORY FILE ---
        print("🔐 Authenticating with Garmin...")
        
        token_filename = "garmin_tokens.txt" #
        
        # Verify the file exists in the current directory
        if not os.path.exists(token_filename):
            print(f"❌ ERROR: File '{token_filename}' not found!")
            print(f"   Visible files in current folder: {os.listdir('.')}")
            sys.exit(1)
            
        # Read the file directly
        with open(token_filename, "r", encoding="utf-8") as file:
            raw_content = file.read().strip()
            
        # Aggressively clean the content to avoid "0 characters" errors
        clean_token = super_clean_base64(raw_content)
        print(f"   -> Raw String Length: {len(raw_content)} chars.")
        print(f"   -> Cleaned Token Length: {len(clean_token)} chars.")

        if len(clean_token) < 10:
            print("❌ ERROR: The token file appears to be empty or corrupted!")
            sys.exit(1)

        # --- STEP B: LOGIN TO GARMIN ---
        try:
            # Decode the clean string into a Garmin session
            decoded_bytes = base64.b64decode(clean_token)
            garth.client.loads(decoded_bytes.decode())
            
            # Start the active Garmin client
            client = Garmin()
            client.garth = garth.client
            print("   -> Success: Logged into Garmin.\n")
        except Exception as auth_err:
            print(f"❌ AUTH ERROR: Decryption failed. Details: {auth_err}")
            sys.exit(1)
        
        # --- STEP C: FETCH DATA (Central Standard Time) ---
        CST = timezone(timedelta(hours=-6)) #
        now = datetime.now(CST)
        today_str = now.date().isoformat()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"📅 Fetching health data for: {today_str}")
        health_data = {
            "timestamp": timestamp,
            "sleep": client.get_sleep_data(today_str),
            "body_battery": client.get_body_battery(today_str)
        } #

        # --- STEP D: UPLOAD TO GOOGLE DRIVE ---
        print("\n☁️ Connecting to Google Drive...")
        creds_info = json.loads(os.environ["GDRIVE_JSON"]) #
        folder_id = os.environ["GDRIVE_FOLDER_ID"] #
        
        # Authenticate with Google Service Account
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare file metadata and the data stream
        file_metadata = {'name': f"health_{timestamp}.json", 'parents': [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(health_data, indent=2).encode()), 
            mimetype='application/json'
        )
        
        # Execute the upload
        uploaded = service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ MISSION COMPLETE: File ID {uploaded.get('id')}")

    except Exception as global_err:
        print(f"\n❌ CRITICAL SYSTEM ERROR: {global_err}")
        sys.exit(1)

if __name__ == "__main__":
    run_sync()
