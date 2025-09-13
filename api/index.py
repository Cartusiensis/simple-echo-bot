import os
import json
import re
from http.server import BaseHTTPRequestHandler
import requests
import pandas as pd
from lib.report_generator import generate_report_text, get_gspread_client
from lib.report_generator import send_telegram_message as send_chunked_message
from lib.report_generator import generate_report_text, get_sheet_as_dataframe


def format_incident_details(incident_data):
    def esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    lines = [f"📄 Detail Ticket: <code>{esc(incident_data.get('incident', 'N/A'))}</code>"]
    field_map = {
        '• Contact Name': 'contact name', '• No. HP': 'no. hp', '• User': 'user',
        '• Customer Type': 'customer type', '• DATEK': 'datek', '• STO': 'sto',
        '• Status Sugar': 'status sugar', '• Proses TTR 4 Jam': 'proses ttr 4 jam', '• SN': 'sn'
    }
    for label, col_name in field_map.items():
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

            # --- NEW: Check for the /report command ---
            if text == "/report":
                send_chunked_message(chat_id, "Generating report, please wait...")
                success, report_text = generate_report_text()
                send_chunked_message(chat_id, report_text)
                # We are done, so we exit early
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return

            # --- Original logic for searching incidents ---
            incident_ids = re.findall(r'\binc\d+\b', text, re.IGNORECASE)
            if not incident_ids:
                # If it's not the report command and not an incident, we can ignore it
                self.send_response(200)
                self.end_headers()
                return

            unique_ids = sorted(list(set(id.upper() for id in incident_ids)))
            SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
            df = get_sheet_as_dataframe(SPREADSHEET_ID, "SQM")
            df['incident'] = df['incident'].str.upper()

            replies = []
            for incident_id in unique_ids:
                result = df[df['incident'] == incident_id]
                if not result.empty:
                    incident_data = result.iloc[0].to_dict()
                    replies.append(format_incident_details(incident_data))
                else:
                    replies.append(f"❌ Tidak ditemukan: <code>{incident_id}</code>")
            
            final_reply = "\n\n".join(replies)
            send_chunked_message(chat_id, final_reply)

        except Exception as e:
            print(f"Error: {e}")
            admin_chat_id = os.environ.get("MY_CHAT_ID")
            if admin_chat_id:
                send_chunked_message(admin_chat_id, f"Bot Error in main handler: {e}")

        # ALWAYS reply to Telegram with a 200 OK
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
        return
