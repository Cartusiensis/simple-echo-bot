import os
import json
import requests
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# --- Reusable function to get an authorized gspread client ---
def get_gspread_client():
    try:
        creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        creds_info = json.loads(creds_json_str)
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error loading Google credentials: {e}")
        return None

# --- Reusable function to send a message ---
def send_telegram_message(chat_id, text):
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)

# --- Function for reading data ---
def get_sheet_as_dataframe(spreadsheet_id, sheet_name):
    gc = get_gspread_client()
    if not gc:
        raise ConnectionError("Google Sheets client is not authorized.")
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [col.strip().lower() for col in df.columns]
    return df

# --- The Core Report Generation Logic ---
def generate_report_text():
    """
    Fetches data from Google Sheets and returns the formatted report as a string.
    Returns a tuple: (success: bool, report_text: str)
    """
    SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
    SHEET_NAME = "SQM"
    TIMEZONE = "Asia/Tokyo"
    THRESHOLD_UMUR = int(os.environ.get("UMUR_THRESHOLD", "12"))

    gc = get_gspread_client()
    if not gc:
        return (False, "Bot Error: Could not authorize with Google Sheets.")

    try:
        df = get_sheet_as_dataframe(SPREADSHEET_ID, SHEET_NAME)

        # --- Filtering and Sorting Logic (same as before) ---
        required_cols = ['status', 'umur tiket', 'incident']
        for col in required_cols:
            if col not in df.columns:
                return (False, f"Error: Column '{col}' not found in spreadsheet.")

        df_open = df[df['status'].str.strip().str.upper() == 'OPEN'].copy()
        df_open['umur_numeric'] = pd.to_numeric(df_open['umur tiket'], errors='coerce')
        df_filtered = df_open[df_open['umur_numeric'] < THRESHOLD_UMUR]
        df_sorted = df_filtered.sort_values(by='umur_numeric', ascending=True)

        # --- Formatting the Message ---
        tz = pytz.timezone(TIMEZONE)
        dt_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
        header = f"⏰ Laporan Tiket — {dt_str}\n"

        if df_sorted.empty:
            body = "Tidak ada tiket yang memenuhi kriteria."
        else:
            rows = []
            for _, row in df_sorted.iterrows():
                incident = row.get('incident', '')
                umur = row.get('umur tiket', '')
                cust_type = row.get('customer type', '')
                sto = row.get('sto', '')
                rows.append(f"<code>{incident}</code> | {umur} Jam | {cust_type} | {sto}")
            body = "\n".join(rows)
        
        return (True, header + "\n" + body)

    except Exception as e:
        print(f"Error during report generation: {e}")
        return (False, f"Bot Error: An exception occurred during report generation: {e}")
