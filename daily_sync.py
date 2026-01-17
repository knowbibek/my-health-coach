# ==============================================================================
# IMPORT LIBRARIES
# These are the tools the robot needs to do its job.
# ==============================================================================
import json         # Used to format data into readable text files
import os           # Used to talk to the computer (read Secrets, check folders)
import sys          # Used to stop the program if something goes wrong
import base64       # Used to decode the secret login token
import io           # Used to handle file data in memory before uploading

# Time tools to figure out "Today" and "Central Standard Time"
from datetime import date, datetime, timezone, timedelta

# Garmin tools to fetch your health stats
from garminconnect import Garmin
import garth

# Google Drive tools to upload the file
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
# SETTINGS: PRIVACY & CLEANUP
# ==============================================================================

# LIST 1: Bloat Removal
# These are useless data fields Garmin sends that take up space.
# We delete them to keep your files small and clean.
KEYS_TO_DELETE = [
    'sleepMovement', 'remSleepData', 'sleepLevels', 'sleepRestlessMoments',
    'wellnessEpochSPO2DataDTOList', 'wellnessEpochRespirationDataDTOList',
    'wellnessEpochRespirationAveragesList', 'sleepHeartRate', 'hrvData',
    'breathingDisruptionData', 'bodyBatteryValuesArray', 
    'bodyBatteryValueDescriptorDTOList', 'wellnessSpO2SleepSummaryDTO',
    'sleepStress', 'sleepBodyBattery', 'userProfilePK', 'deviceId', 
    'matchId', 'campaignId', 'sleepResultTypePK', 'sleepQualityTypePK', 
    'partiallyIndexed', 'autoSleepStartTimestampGMT', 
    'autoSleepEndTimestampGMT', 'sleepStartTimestampGMT', 
    'sleepEndTimestampGMT', 'calendarDate', 'userProfilePk'
]

# LIST 2: Privacy Shield
# These are words that might reveal your location or identity.
# If we see these in the data, we delete that specific piece of info.
PRIVACY_TRIGGERS = [
    'latitude', 'longitude', 'lat', 'lon', 'location', 
    'city', 'address', 'neighborhood', 'postal', 'zip', 'deviceid', 
    'userprofilepk', 'pk', 'matchid', 'campaignid'
]

# FUNCTION: Scrub Data
# This helper function looks through the data dictionary.
# If it finds "trash" keys (List 1) or "sensitive" keys (List 2), it removes them.
def scrub_data(data):
    # If the data is a Dictionary (key: value pairs)...
    if isinstance(data, dict):
        clean_dict = {}
        for key, value in data.items():
            # Check if this key is in our "Delete List"
            if key in KEYS_TO_DELETE: 
                continue # Skip it (Delete it)
            
            # Check if this key sounds like private info (Location/ID)
            is_sensitive = False
            for trigger in PRIVACY_TRIGGERS:
                if trigger in key.lower():
                    is_sensitive = True
                    break
            
            if is_sensitive: 
                continue # Skip it (Delete it)
            
            # If safe, clean the value inside (recursive) and keep it
            clean_dict[key] = scrub_data(value)
        return clean_dict
    
    # If the data is a List (items in a row)...
    elif isinstance(data, list):
        # Clean every single item in the list
        return [scrub_data(item) for item in data]
    
    # If it's just text or a number, keep it as is.
    return data

# ==============================================================================
# FUNCTION: UPLOAD TO GOOGLE DRIVE
# This handles the connection to Google and sending the file.
# ==============================================================================
def upload_to_drive(data_dict, filename):
    try:
        print("☁️ Connecting to Google Drive...")
        
        # 1. Get the Robot's ID Card (JSON Key) from GitHub Secrets
        key_json = os.environ["GDRIVE_JSON"]
        service_account_info = json.loads(key_json)
        
        # 2. Login to Google Drive
        creds = Credentials.from_service_account_info(service_account_info)
        service = build('drive', 'v3', credentials=creds)
        
        # 3. Get the specific Folder ID where we want to drop the file
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        
        # 4. Prepare the File Metadata (Name and Location)
        file_metadata = {
            'name': filename,
            'parents': [folder_id] # Put it inside this specific folder
        }
        
        # 5. Convert our Data Dictionary into a File format
        # This converts the JSON text into a "stream" that looks like a file to Google
        file_stream = io.BytesIO(json.dumps(data_dict, indent=2).encode('utf-8'))
        media = MediaIoBaseUpload(file_stream, mimetype='application/json')
        
        # 6. Execute the Upload
        new_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"   -> Upload Success! File ID: {new_file.get('id')}")
        return True # Report success

    except Exception as error_message:
        print(f"❌ DRIVE UPLOAD FAILED: {error_message}")
        return False # Report failure

# ==============================================================================
# MAIN ROBOT LOGIC
# This is the "Main" script that runs when the robot wakes up.
# ==============================================================================
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # STEP 1: AUTHENTICATION (Login without Password)
        print("🔐 Authenticating with Garmin...")
        
        # Get the secret token string from GitHub
        token_str = os.environ.get("GARMIN_TOKENS")
        
        # Safety Check: Did we forget to add the secret?
        if not token_str:
            print("❌ ERROR: GARMIN_TOKENS secret is missing!")
            sys.exit(1) # Stop everything
            
        # Decode the token and give it to the library
        garth.client.loads(base64.b64decode(token_str).decode())
        
        # Initialize the Garmin client
        client = Garmin()
        client.garth = garth.client
        client.display_name = "User" # Generic name
        print("   -> Success. Logged in.\n")
        
        # STEP 2: SETUP TIME (Central Standard Time)
        # We need to know what "Today" is in Texas, not in the Cloud server.
        CST = timezone(timedelta(hours=-6)) # CST is UTC -6 hours
        now_cst = datetime.now(CST)
        
        today_date = now_cst.date().isoformat()         # Format: 2024-01-01
        timestamp = now_cst.strftime("%Y-%m-%d_%H-%M-%S") # Format: 2024-01-01_13-30-00
        
        print(f"📅 Target Date: {today_date}")
        print(f"🕒 Timestamp:   {timestamp} (CST)\n")
        
        # Create a container for our data
        data_packet = {
            "timestamp": timestamp,
            "date_query": today_date
        }

        # STEP 3: FETCH DATA
        # Attempt to get Sleep Data
        try:
            data_packet["sleep"] = client.get_sleep_data(today_date)
            print("   [+] Sleep Data Found")
        except: 
            print("   [-] Sleep Data Not Found (Maybe you are awake?)")

        # Attempt to get Body Battery Data
        try:
            data_packet["body_battery"] = client.get_body_battery(today_date)
            print("   [+] Body Battery Found")
        except: 
            print("   [-] Body Battery Not Found")

        # STEP 4: CLEAN & UPLOAD
        # Only upload if we actually found data (length > 2 means we have more than just the timestamp)
        if len(data_packet) > 2:
            print("\n🧹 Scrubbing Data for Privacy...")
            
            # Run the cleaning function
            clean_payload = scrub_data(data_packet)
            
            # Create the filename
            filename = f"health_{timestamp}.json"
            
            # Send it to Google Drive
            success = upload_to_drive(clean_payload, filename)
            
            if success:
                print(f"\n✅ MISSION COMPLETE: File saved to 'gemini_health'")
            else:
                sys.exit(1) # Fail so GitHub sends an alert
        else:
            print("\n❌ FAILURE: No data retrieved from Garmin.")
            sys.exit(1)

    except Exception as global_error:
        print(f"\n❌ CRITICAL ERROR: {global_error}")
        sys.exit(1)

# This tells Python: "Start here!"
if __name__ == "__main__":
    run_sync()
