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
# Words that might reveal your location or identity. We remove these.
PRIVACY_TRIGGERS = [
    'latitude', 'longitude', 'lat', 'lon', 'location', 
    'city', 'address', 'neighborhood', 'postal', 'zip', 'deviceid', 
    'userprofilepk', 'pk', 'matchid', 'campaignid'
]

def scrub_data(data):
    """
    Recursively removes 'trash' keys and sensitive privacy data from the Garmin results.
    """
    if isinstance(data, dict):
        clean_dict = {}
        for key, value in data.items():
            # Skip if the key is in our delete list
            if key in KEYS_TO_DELETE: 
                continue
            
            # Skip if the key sounds like a privacy trigger (like 'latitude')
            is_sensitive = any(trigger in key.lower() for trigger in PRIVACY_TRIGGERS)
            if is_sensitive: 
                continue
            
            # Otherwise, keep cleaning and add to our clean dictionary
            clean_dict[key] = scrub_data(value)
        return clean_dict
    elif isinstance(data, list):
        return [scrub_data(item) for item in data]
    return data

# ==============================================================================
# FUNCTION: UPLOAD TO GOOGLE DRIVE
# ==============================================================================
def upload_to_drive(data_dict, filename):
    """
    Connects to Google Drive using a Service Account and uploads the JSON data.
    """
    try:
        print("☁️ Connecting to Google Drive...")
        
        # 1. Load the Service Account credentials from GitHub Secrets
        key_json = os.environ["GDRIVE_JSON"]
        service_account_info = json.loads(key_json)
        
        # 2. Authorize and build the Drive service
        creds = Credentials.from_service_account_info(service_account_info)
        service = build('drive', 'v3', credentials=creds)
        
        # 3. Target the specific folder ID from your secrets
        folder_id = os.environ["GDRIVE_FOLDER_ID"]
        
        # 4. Set the file metadata (name and parent folder)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        
        # 5. Convert our data into a byte stream for upload
        file_stream = io.BytesIO(json.dumps(data_dict, indent=2).encode('utf-8'))
        media = MediaIoBaseUpload(file_stream, mimetype='application/json')
        
        # 6. Perform the upload
        new_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"   -> Upload Success! File ID: {new_file.get('id')}")
        return True

    except Exception as error_message:
        print(f"❌ DRIVE UPLOAD FAILED: {error_message}")
        return False

# ==============================================================================
# MAIN ROBOT LOGIC
# ==============================================================================
def run_sync():
    print(f"{'='*40}\n   GARMIN -> GOOGLE DRIVE AUTOMATION\n{'='*40}\n")
    
    try:
        # STEP 1: AUTHENTICATION
        print("🔐 Authenticating with Garmin...")
        
        # Get both halves of the split token from GitHub
        part1 = os.environ.get("GARMIN_PART1", "")
        part2 = os.environ.get("GARMIN_PART2", "")
        
        # Re-assemble the pieces into the full key
        token_str = part1 + part2
        
        if not token_str:
            print("❌ ERROR: Secrets GARMIN_PART1 and GARMIN_PART2 are missing!")
            sys.exit(1)
            
        print(f"   -> Token assembled. Total Length: {len(token_str)} chars.")

        try:
            # Decode the base64 string and load the session into garth
            decoded_token = base64.b64decode(token_str).decode()
            garth.client.loads(decoded_token)
        except Exception as e:
            print(f"❌ TOKEN ERROR: Could not read the secret key. Details: {e}")
            sys.exit(1)
        
        # Start the Garmin client
        client = Garmin()
        client.garth = garth.client
        client.display_name = "User"
        print("   -> Success. Logged in.\n")
        
        # STEP 2: SETUP TIME (Central Standard Time)
        CST = timezone(timedelta(hours=-6))
        now_cst = datetime.now(CST)
        
        today_date = now_cst.date().isoformat()
        timestamp = now_cst.strftime("%Y-%m-%d_%H-%M-%S")
        
        print(f"📅 Target Date: {today_date}")
        print(f"🕒 Timestamp:   {timestamp} (CST)\n")
        
        # Prepare the container for our data
        data_packet = {
            "timestamp": timestamp,
            "date_query": today_date
        }

        # STEP 3: FETCH DATA
        # Try to get Sleep stats
        try:
            data_packet["sleep"] = client.get_sleep_data(today_date)
            print("   [+] Sleep Data Found")
        except: 
            print("   [-] Sleep Data Not Found")

        # Try to get Body Battery stats
        try:
            data_packet["body_battery"] = client.get_body_battery(today_date)
            print("   [+] Body Battery Found")
        except: 
            print("   [-] Body Battery Not Found")

        # STEP 4: CLEAN & UPLOAD
        # Only upload if we found more than just the timestamp (length > 2)
        if len(data_packet) > 2:
            print("\n🧹 Scrubbing Data for Privacy...")
            clean_payload = scrub_data(data_packet)
            
            # Create a unique filename
            filename = f"health_{timestamp}.json"
            
            # Send to Drive
            success = upload_to_drive(clean_payload, filename)
            
            if success:
                print(f"\n✅ MISSION COMPLETE: File saved to 'gemini_health'")
            else:
                sys.exit(1)
        else:
            print("\n❌ FAILURE: No data retrieved from Garmin.")
            sys.exit(1)

    except Exception as global_error:
        print(f"\n❌ CRITICAL ERROR: {global_error}")
        sys.exit(1)

# Wake up the robot!
if __name__ == "__main__":
    run_sync()
