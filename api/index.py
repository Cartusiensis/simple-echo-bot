import os
import json
from http.server import BaseHTTPRequestHandler
import requests # We will use this library

# This function is the entry point for all requests on Vercel
class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # 1. READ THE INCOMING MESSAGE FROM TELEGRAM
            # Get the size of the incoming data
            content_length = int(self.headers['Content-Length'])
            # Read the data itself
            post_data = self.rfile.read(content_length)
            # Parse the JSON data into a Python dictionary
            update = json.loads(post_data)

            # 2. EXTRACT THE NECESSARY INFO
            chat_id = update["message"]["chat"]["id"]
            received_text = update["message"]["text"]

            # 3. PREPARE THE REPLY
            # Get the Bot Token from an Environment Variable for security
            BOT_TOKEN = os.environ.get("BOT_TOKEN")
            if not BOT_TOKEN:
                raise ValueError("BOT_TOKEN is not set!")

            reply_text = f"You sent me: {received_text}"
            
            # 4. SEND THE REPLY BACK TO TELEGRAM
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": reply_text
            }
            # Make the request to the Telegram API
            requests.post(url, json=payload)

        except Exception as e:
            # Log any errors to the Vercel logs for debugging
            print(f"Error: {e}")

        # 5. SEND A "200 OK" RESPONSE
        # This is crucial. It tells Telegram "I got your message, thank you."
        # This prevents the 302 redirect or timeout errors you saw with GAS.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
        return