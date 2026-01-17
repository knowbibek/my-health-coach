# 🛠️ Setup & Maintenance Guide

Use this guide if your authentication tokens expire or if you need to set up the automation from scratch.

---

## 0️⃣ PRE-REQUISITE: Get `credentials.json` (First Time Only)

To allow the automation to save files to Google Drive, you need a "Desktop" credential file.

1.  Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2.  **Create a Project:** Name it "Health Sync" (or similar) > **Create**.
3.  **Enable Drive API:**
    * Click **"APIs & Services"** > **"Library"**.
    * Search for **"Google Drive API"**.
    * Click **Enable**.
4.  **Configure Consent Screen:**
    * Go to **"OAuth consent screen"** (left sidebar).
    * Select **External** > **Create**.
    * **App Name:** "Garmin Sync" | **Support Email:** Select your email.
    * Skip the "Scopes" page (Click Save).
    * **Test Users (CRITICAL):** Click **+ ADD USERS** and enter the Gmail address you plan to use for storage. (If you skip this, login will fail).
5.  **Create Keys:**
    * Go to **"Credentials"** (left sidebar).
    * Click **+ CREATE CREDENTIALS** > **OAuth client ID**.
    * **Application type:** Select **Desktop app**.
    * Name: "Garmin Desktop".
    * Click **Create**.
6.  **Download:** A popup will appear. Click **DOWNLOAD JSON** and rename the file to `credentials.json`.

---

# 2 Google Drive Setup Guide

This section explains how to generate the `GDRIVE_OAUTH_JSON` secret needed for the automation to access your Google Drive.

---

### **Step 0: Get `credentials.json` (First Time Only)**
To allow the automation to save files, you need a "Desktop" credential file from Google.

1.  Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2.  **Create a Project:** Name it "Health Sync" > **Create**.
3.  **Enable Drive API:**
    * Click **"APIs & Services"** > **"Library"**.
    * Search for **"Google Drive API"**.
    * Click **Enable**.
4.  **Configure Consent Screen:**
    * Go to **"OAuth consent screen"** (left sidebar).
    * Select **External** > **Create**.
    * **App Name:** "Garmin Sync" | **Support Email:** Select your email.
    * Skip the "Scopes" page (Click Save).
    * **Test Users (CRITICAL):** Click **+ ADD USERS** and enter the Gmail address you plan to use for storage. (If you skip this, login will fail).
5.  **Create Keys:**
    * Go to **"Credentials"** (left sidebar).
    * Click **+ CREATE CREDENTIALS** > **OAuth client ID**.
    * **Application type:** Select **Desktop app**.
    * Name: "Garmin Desktop".
    * Click **Create**.
6.  **Download:** A popup will appear. Click **DOWNLOAD JSON** and rename the file to `credentials.json`.

---

### **Step 1: Generate the Token**
Use this script to authorize the robot to upload files to your specific folder.

1.  Open **[Google Colab](https://colab.research.google.com/)**.
2.  **Upload** your `credentials.json` file to the folder icon 📁 on the left.
3.  Paste and run this code:

```python
# --- STEP 1: INSTALL LIBRARIES ---
!pip install google-auth-oauthlib -q
from google_auth_oauthlib.flow import InstalledAppFlow
from google.colab import files
import os

# Check if file exists
if not os.path.exists('credentials.json'):
    print("❌ ERROR: Please upload 'credentials.json' to the folder on the left!")
else:
    # --- STEP 2: AUTHENTICATE ---
    # This scope allows creating NEW files but keeps the rest of your drive private
    SCOPES = ['[https://www.googleapis.com/auth/drive.file](https://www.googleapis.com/auth/drive.file)']
    
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', 
        SCOPES,
        redirect_uri='http://localhost:8080/'
    )

    # Generate Login Link
    auth_url, _ = flow.authorization_url(prompt='consent')

    print("👇 CLICK THIS LINK TO LOGIN 👇")
    print(auth_url)
    print("\nINSTRUCTIONS:")
    print("1. Click the link above and login with your Google Account.")
    print("2. If warned 'Google hasn't verified this app', click Advanced > Go to App (Unsafe).")
    print("3. When the page says 'This site can't be reached', LOOK AT THE URL BAR.")
    print("4. COPY the text starting after 'code='.")

    # --- STEP 3: PASTE CODE ---
    code = input("\nPaste the URL code here: ").strip()
    
    try:
        flow.fetch_token(code=code)
        print("\n✅ SUCCESS! Copy the ENTIRE JSON below into GitHub Secret 'GDRIVE_OAUTH_JSON':")
        print("="*60)
        print(flow.credentials.to_json())
        print("="*60)
    except Exception as e:
        print(f"❌ Error: {e}")


```


---

## 2️⃣ Garmin Token Generator

**Purpose:** Garmin session tokens are very long (~5,000 characters). This script logs you in and splits the token into 3 parts so they fit into GitHub Secrets.

**Note on MFA:** If Garmin detects a new login, this script will pause and ask you to enter the MFA code sent to your email.

**Steps:**
1.  Open **[Google Colab](https://colab.research.google.com/)**.
2.  Paste and run this code:

```python
# --- STEP 1: INSTALL LIBRARIES ---
!pip install garth requests -q

# --- STEP 2: GENERATE & SPLIT ---
import base64
import garth

# Login (Interactive)
print("Enter your Garmin Connect credentials:")
email = input("Email: ")
password = input("Password: ")

try:
    # This will automatically ask for MFA if Garmin requires it
    garth.login(email, password)
    
    # Export & Encode
    session_string = garth.client.dumps()
    token = base64.b64encode(session_string.encode()).decode()

    # Split into 3 Safe Parts (to bypass GitHub character limits)
    chunk_size = len(token) // 3
    p1 = token[:chunk_size]
    p2 = token[chunk_size:2*chunk_size]
    p3 = token[2*chunk_size:]

    print(f"\n✅ SUCCESS! Garmin Token Generated (Length: {len(token)})")
    print("\n👇 Create these 3 Secrets in GitHub Settings 👇\n")
    print("="*20 + "\nName: GARMIN_PART1\nValue:\n" + p1 + "\n" + "="*20)
    print("="*20 + "\nName: GARMIN_PART2\nValue:\n" + p2 + "\n" + "="*20)
    print("="*20 + "\nName: GARMIN_PART3\nValue:\n" + p3 + "\n" + "="*20)

except Exception as e:
    print(f"\n❌ Login Failed: {e}")
