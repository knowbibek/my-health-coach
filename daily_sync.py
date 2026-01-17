# ==============================================================================
#  GARMIN -> DRIVE SYNC ROBOT (Readable & Privacy Focused)
# ==============================================================================
#  Features:
#  1. AUTH: Uses a 3-part secret to bypass character limits.
#  2. PRIVACY: Strips out massive raw data arrays (Movement, SpO2, etc).
#  3. STORAGE: Saves tiny, clean JSON files with CST timestamps.
# ==============================================================================

import json
import os
import sys
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# --- Third-Party Libraries ---
from garminconnect import Garmin
import garth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
#  SECTION 1: HELPER FUNCTIONS
# ==============================================================================

def clean_token_string(raw_string):
    """
    Cleans the secret token by removing invisible characters (spaces/newlines)
    and fixing the padding required for Base64 decoding.
    """
    # Remove any character that isn't a valid Base64 character
    cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', raw_string)
    
    # Add '=' padding until the length is a multiple of 4
    while len(cleaned) % 4 != 0:
        cleaned += '='
    return cleaned

def filter_health_data(raw_sleep, raw_bb):
    """
    THE DATA DIET:
    Takes the massive raw data and extracts ONLY the summary numbers.
    This effectively deletes thousands of lines of noise.
    """
    # --- A. Process Sleep Data ---
    # We safely extract nested dictionaries using .get()
    sleep_dto = raw_sleep.get('dailySleepDTO', {})
    scores = sleep_dto.get('sleepScores', {})
    
    # Convert seconds to a readable "Xh Ym" format
    total_seconds = sleep_dto.get('sleepTimeSeconds', 0)
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)

    clean_sleep = {
        "date": sleep_dto.get('calendarDate'),
        "duration": f"{hours}h {minutes}m",
        "score": scores.get('overall', {}).get('value'),
        "quality": scores.get('overall', {}).get('qualifierKey'),  # e.g., "POOR"
        "deep_sleep_min": int(sleep_dto.get('deepSleepSeconds', 0) // 60),
        "rem_sleep_min": int(sleep_dto.get('remSleepSeconds', 0) // 60),
        "awake_count": sleep_dto.get('awakeCount'),
        "avg_stress": sleep_dto.get('avgSleepStress'),
        "avg_hrv": raw_sleep.get('sleepData', {}).get('avgOvernightHrv'),
        "resting_hr": sleep_dto.get('restingHeartRate')
    }

    # --- B. Process Body Battery ---
    # Garmin provides a list of days; we grab the first one (today)
    clean_bb = {"status": "No data available"}
    
    if isinstance(raw_bb, list) and len(raw_bb) > 0:
        day_data = raw_bb[0]
        
        # The 'values' array is a graph of [timestamp, level]. 
        # We want the LAST item in the list to get the current level.
        graph = day_data.get('bodyBatteryValuesArray', [])
        current_val = graph[-1][1] if graph else "N/A"
        
        clean_bb = {
            "current_level": current_val,
            "charged": day_data.get('charged'),
            "drained": day_data.get('drained')
        }

    # Combine the clean sections into one small package
    return {
        "sleep": clean_sleep,
        "body_battery": clean_bb
    }

# ==============================================================================
#  SECTION 2: MAIN EXECUTION FLOW
# ==============================================================================
