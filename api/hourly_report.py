import os
from http.server import BaseHTTPRequestHandler
# Vercel allows us to import from other folders like this
from lib.report_generator import generate_report_text, send_telegram_message

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
        if not MY_CHAT_ID:
            print("MY_CHAT_ID is not set. Cannot send report.")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Admin chat ID not configured.")
            return

        # Generate the report text by calling our shared function
        success, report_text = generate_report_text()
        
        # Send the result to the admin chat
        send_telegram_message(MY_CHAT_ID, report_text)
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Report generation triggered.")
        return