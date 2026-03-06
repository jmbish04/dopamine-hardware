import json
import time
import logging
import requests
import websocket
from config import WS_URL, WORKER_URL
from hardware import print_and_ack

def run_websocket():
    def on_message(ws, message):
        data = json.loads(message)
        logging.info(f"⚡ [WS] Received job: {data['id']}")
        print_and_ack(data['id'], data['title'])
    def on_error(ws, error): pass
    def on_close(ws, close_status_code, close_msg):
        logging.warning("⚠️ [WS] Disconnected. Reconnecting in 5s...")
        time.sleep(5)
        run_websocket()
    ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

def run_rest_polling():
    while True:
        try:
            res = requests.get(f"{WORKER_URL}/api/printer/pending", timeout=10)
            if res.status_code == 200:
                for job in res.json():
                    logging.info(f"🔄 [POLL] Found missed job: {job['id']}")
                    print_and_ack(job['id'], job['title'])
        except Exception:
            pass
        time.sleep(15)
