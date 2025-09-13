import os
import json
import re
from http.server import BaseHTTPRequestHandler
import requests
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
# These will be set as Environment Variables in Vercel
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
SHEET_NAME = "SQM" # The name of the specific tab/sheet
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Load Google credentials from the environment variable
try:
    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    creds_info = json.loads(creds_json_str)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)
except (json.JSONDecodeError, TypeError) as e:
    print(f"Error loading Google credentials: {e}")
    gc = None # Set gc to None if auth fails

# --- HELPER FUNCTIONS ---

def send_chunked_message(chat_id, text, chunk_size=3500):
    """Splits long messages to stay under Telegram's character limit."""
    if len(text) <= chunk_size:
        send_message(chat_id, text)
        return

    # Split by newline to avoid breaking in the middle of a line
    lines = text.split('\n')
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > chunk_size:
            send_message(chat_id, current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    if current_chunk:
        send_message(chat_id, current_chunk)

def send_message(chat_id, text):
    """Sends a message to a specific chat ID via the Telegram Bot API."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)

def get_sheet_as_dataframe(spreadsheet_id, sheet_name):
    """Reads the entire sheet into a powerful pandas DataFrame."""
    if not gc:
        raise ConnectionError("Google Sheets client is not authorized.")
    spreadsheet = gc.open_by_key(spreadsheet_id)
    sheet = spreadsheet.worksheet(sheet_name)
    # get_all_records() is a great gspread function that returns a list of dictionaries
    data = sheet.get_all_records()
    # Convert to a DataFrame for easy searching and filtering
    df = pd.DataFrame(data)
    # Convert all column names to lowercase and strip whitespace for easier access
    df.columns = [col.strip().lower() for col in df.columns]
    return df

def format_incident_details(incident_data):
    """Formats the ticket details for the reply message (similar to your formatIncidentDetails_)."""
    # Helper to escape HTML characters
    def esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Map your DataFrame column names (lowercase) to the data
    lines = [f"📄 Detail Ticket: <code>{esc(incident_data.get('incident', 'N/A'))}</code>"]
    
    # Define mappings from your desired output to the DataFrame columns
    field_map = {
        '• Contact Name': 'contact name',
        '• No. HP': 'no. hp',
        '• User': 'user',
        '• Customer Type': 'customer type',
        '• DATEK': 'datek',
        '• STO': 'sto',
        '• Status Sugar': 'status sugar',
        '• Proses TTR 4 Jam': 'proses ttr 4 jam',
        '• SN': 'sn'
    }

    for label, col_name in field_map.items():
        # Check if the column exists in our data and has a value
        if col_name in incident_data and pd.notna(incident_data[col_name]) and incident_data[col_name] != '':
            lines.append(f"{label}: {esc(incident_data[col_name])}")
            
    return "\n".join(lines)

# --- VERCEL'S MAIN HANDLER ---

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data)

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip()

            if not chat_id or not text:
                self.send_response(200)
                self.end_headers()
                return

            # Find all "INC..." numbers in the message
            incident_ids = re.findall(r'\binc\d+\b', text, re.IGNORECASE)
            if not incident_ids:
                self.send_response(200)
                self.end_headers()
                return

            # Remove duplicates and convert to uppercase
            unique_ids = sorted(list(set(id.upper() for id in incident_ids)))

            # Fetch the entire sheet data once
            df = get_sheet_as_dataframe(SPREADSHEET_ID, SHEET_NAME)
            # Make the 'incident' column uppercase for case-insensitive matching
            df['incident'] = df['incident'].str.upper()

            replies = []
            for incident_id in unique_ids:
                # Search for the incident in the DataFrame
                result = df[df['incident'] == incident_id]
                
                if not result.empty:
                    # Get the first matching row as a dictionary
                    incident_data = result.iloc[0].to_dict()
                    replies.append(format_incident_details(incident_data))
                else:
                    replies.append(f"❌ Tidak ditemukan: <code>{incident_id}</code>")
            
            # Join all individual replies into one big message
            final_reply = "\n\n".join(replies)
            send_chunked_message(chat_id, final_reply)

        except Exception as e:
            # For debugging, send the error back to yourself if you have a CHAT_ID set
            print(f"Error: {e}")
            admin_chat_id = os.environ.get("MY_CHAT_ID")
            if admin_chat_id:
                send_message(admin_chat_id, f"Bot Error: {e}")

        # ALWAYS reply to Telegram with a 200 OK
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
        return
