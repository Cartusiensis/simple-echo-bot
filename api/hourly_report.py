import os
import json
from http.server import BaseHTTPRequestHandler
import requests
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz # For handling timezones

# --- CONFIGURATION (from Environment Variables) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID") # The chat to send the report to
SHEET_NAME = "SQM"
TIMEZONE = "Asia/Tokyo"
THRESHOLD_UMUR = 24 # filter: UMUR TIKET < 24
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --- GOOGLE SHEETS AUTHENTICATION (same as index.py) ---
try:
    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    creds_info = json.loads(creds_json_str)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)
except Exception as e:
    print(f"Error loading Google credentials: {e}")
    gc = None

# --- HELPER FUNCTIONS (same as index.py, but simplified for the report) ---
def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)

def get_sheet_as_dataframe(spreadsheet_id, sheet_name):
    if not gc:
        raise ConnectionError("Google Sheets client is not authorized.")
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [col.strip().lower() for col in df.columns]
    return df

# --- MAIN REPORT LOGIC ---
def generate_and_send_report():
    if not all([BOT_TOKEN, SPREADSHEET_ID, MY_CHAT_ID]):
        print("Missing one or more required environment variables.")
        return

    try:
        df = get_sheet_as_dataframe(SPREADSHEET_ID, SHEET_NAME)
        
        # Ensure required columns exist, using lowercase names
        required_cols = ['status', 'umur tiket', 'incident']
        for col in required_cols:
            if col not in df.columns:
                send_message(MY_CHAT_ID, f"Error: Column '{col}' not found in spreadsheet.")
                return

        # 1. Filter by STATUS = OPEN (case-insensitive)
        df_open = df[df['status'].str.strip().str.upper() == 'OPEN'].copy()

        # 2. Filter by UMUR TIKET < THRESHOLD
        #    - pd.to_numeric will handle numbers and strings safely
        #    - errors='coerce' turns non-numeric values into NaN (Not a Number)
        df_open['umur_numeric'] = pd.to_numeric(df_open['umur tiket'], errors='coerce')
        df_filtered = df_open[df_open['umur_numeric'] < THRESHOLD_UMUR]

        # 3. Sort by age ascending
        df_sorted = df_filtered.sort_values(by='umur_numeric', ascending=True)

        # 4. Format the message
        tz = pytz.timezone(TIMEZONE)
        dt_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
        header = f"⏰ Laporan Tiket — {dt_str}\n"

        if df_sorted.empty:
            body = "Tidak ada tiket yang memenuhi kriteria."
        else:
            rows = []
            # .get(col, '') is a safe way to access columns that might not exist
            for _, row in df_sorted.iterrows():
                incident = row.get('incident', '')
                umur = row.get('umur tiket', '')
                cust_type = row.get('customer type', '')
                sto = row.get('sto', '')
                rows.append(f"<code>{incident}</code> | {umur} Jam | {cust_type} | {sto}")
            body = "\n".join(rows)
        
        final_message = header + "\n" + body
        send_message(MY_CHAT_ID, final_message)

    except Exception as e:
        print(f"Error generating report: {e}")
        send_message(MY_CHAT_ID, f"Bot Error during hourly report: {e}")


# --- VERCEL HANDLER for CRON JOB ---
# Vercel needs this file to be a serverless function it can call.
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # When Vercel's cron calls this URL, run the report function
        generate_and_send_report()
        
        # Respond with a 200 OK to let Vercel know the job was received.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Report generation triggered.")
        return