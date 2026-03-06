import json
import time
import logging
import requests
import websocket
from config import WS_URL, WORKER_URL
from hardware import print_and_ack

def run_websocket():
    """Maintain WebSocket connection with iterative reconnection logic."""
    while True:  # Use iterative loop instead of recursion
        try:
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    job_id = data.get('receiptQrValue') or data.get('taskId') or data.get('id', 'unknown')
                    logging.info(f"⚡ [WS] Received job: {job_id}")
                    print_and_ack(data)
                except (json.JSONDecodeError, KeyError) as e:
                    logging.error(f"⚠️ [WS] Invalid message format: {e}")
                except Exception as e:
                    logging.error(f"⚠️ [WS] Error processing message: {e}")

            def on_error(ws, error):
                logging.error(f"⚠️ [WS] Error: {error}")

            def on_close(ws, close_status_code, close_msg):
                logging.warning(f"⚠️ [WS] Disconnected (status: {close_status_code}). Reconnecting in 5s...")

            ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_close=on_close)
            ws.run_forever()

            # If run_forever returns, wait before reconnecting
            time.sleep(5)

        except Exception as e:
            logging.error(f"⚠️ [WS] Connection failed: {e}. Reconnecting in 5s...")
            time.sleep(5)

def run_rest_polling():
    """Poll for pending jobs with error logging."""
    while True:
        try:
            res = requests.get(f"{WORKER_URL}/api/printer/pending", timeout=10)
            if res.status_code == 200:
                jobs = res.json()
                for job in jobs:
                    job_id = job.get('receiptQrValue') or job.get('taskId') or job.get('id', 'unknown')
                    logging.info(f"🔄 [POLL] Found missed job: {job_id}")
                    print_and_ack(job)
        except requests.exceptions.RequestException as e:
            logging.warning(f"[POLL] Failed to fetch pending jobs: {e}")
        except Exception as e:
            logging.error(f"[POLL] Unexpected error: {e}")
        time.sleep(15)
