# 🤖 Garmin -> Google Drive Health Sync (AI-Optimized)

A privacy-focused automation robot that fetches daily health metrics from Garmin Connect and syncs a clean, summarized JSON file to a specific Google Drive folder.

**Designed for AI Context:** This tool strips out thousands of lines of raw "noise" (like minute-by-minute movement data) and produces a tiny, token-efficient summary perfect for feeding into LLMs like Gemini or ChatGPT.

---

## ✨ Features

* **🛡️ Privacy First:** Automatically removes sensitive data like device serial numbers, user IDs, and precise location coordinates.
* **🧹 The "Data Diet":** Compresses ~5,000 lines of raw Garmin JSON into ~25 lines of high-value summary metrics.
* **🧠 AI-Ready:** Pre-calculates durations and averages so your AI doesn't have to do math.
* **☁️ User-Mode Storage:** Uses standard OAuth to bypass Service Account "0-byte storage" restrictions.
* **🕒 CST Timezone:** Enforces Central Standard Time (UTC-6) for accurate daily tracking.
* **🔄 Triple-Chunk Auth:** Solves the GitHub Secrets character limit/truncation bug.

---

## 📂 Repository Structure

```text
.
├── .github/workflows/
│   └── sync.yml        # The "Alarm Clock" (Runs every hour)
├── daily_sync.py       # The "Brain" (Fetches, cleans, and uploads data)
├── requirements.txt    # The "Toolbox" (List of Python libraries)
├── README.md           # This file
└── SETUP_GUIDE.md      # Instructions for generating tokens

```

---

## ⚙️ Configuration & Secrets

This project requires **6 Secrets** to be configured in GitHub Actions:

| Secret Name | Description |
| --- | --- |
| `GARMIN_PART1` | The first 1/3rd of your Garmin Session Token. |
| `GARMIN_PART2` | The middle 1/3rd of your Garmin Session Token. |
| `GARMIN_PART3` | The final 1/3rd of your Garmin Session Token. |
| `GDRIVE_OAUTH_JSON` | The "Master Key" for your Google Drive (User Mode). |
| `GDRIVE_FOLDER_ID` | The ID of the folder where files will be saved. |

> **Note:** See `SETUP_GUIDE.md` for the scripts to generate these tokens.

---

## 🚀 How It Works

1. **Trigger:** GitHub Actions wakes up every hour (at minute 0).
2. **Authenticate:**
* Re-assembles the Garmin token from the 3 parts.
* Logs into Google Drive using the OAuth User Credentials.


3. **Fetch & Filter:**
* Downloads raw sleep and body battery data.
* **Filters:** Deletes `sleepMovement`, `dailySleepDTO`, and `wellnessEpoch` arrays.
* **Summarizes:** Extracts only Score, Duration, HRV, Stress, and Body Battery levels.


4. **Upload:**
* Saves a file named `health_YYYY-MM-DD_HH-MM-SS.json` to your Drive.



---

## 📊 Data Output Example

The uploaded file is optimized for low token usage:

```json
{
  "timestamp_cst": "2026-01-17_16-45-00",
  "metrics": {
    "sleep": {
      "date": "2026-01-17",
      "duration": "7h 15m",
      "score": 85,
      "quality": "GOOD",
      "avg_stress": 22.0,
      "avg_hrv": 45.0
    },
    "body_battery": {
      "current": 78,
      "high": 95,
      "low": 25
    }
  }
}

```

```

```


