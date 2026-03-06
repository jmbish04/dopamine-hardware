import logging
import json
import time
import threading
import requests
import websocket
from flask import Flask, request, jsonify
from escpos.printer import Usb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- Configuration ---
VENDOR_ID = 0x04b8
PRODUCT_ID = 0x0e28
WORKER_URL = "https://your-worker-domain.workers.dev" # REPLACE WITH YOUR WORKER URL
WS_URL = "wss://your-worker-domain.workers.dev/api/printer/ws" # REPLACE WITH YOUR WORKER URL

# State to prevent duplicate printing
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID, profile="TM-T20III")
    except Exception as e:
        logging.error(f"Printer error: {e}")
        return None

def print_and_ack(job_id, title):
    """Core print logic. Used by VPC, WebSockets, and REST."""
    if job_id in printed_jobs:
        return True # Already printed
        
    with printer_lock:
        p = get_printer()
        if not p:
            return False

        try:
            p.hw("INIT")
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("ONION TASKER\n")
            p.set(align='center', font='a', width=1, height=1)
            p.text("-" * 32 + "\n\n")
            p.set(align='left')
            p.text(f"ID: {job_id}\n")
            p.set(bold=True)
            p.text(f"Task: {title}\n\n")
            p.set(bold=False)
            p.set(align='center')
            p.qr(job_id, size=8, native=True)
            p.text("\n\n\n")
            p.cut()
            p.close()
            
            printed_jobs.add(job_id)
            logging.info(f"Successfully printed: {job_id}")
            
            # Ack back to the worker
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id})
            return True
        except Exception as e:
            logging.error(f"Print failed: {e}")
            if p: p.close()
            return False

# ==========================================
# TIER 1: VPC Flask Server (Sub-millisecond)
# ==========================================
@app.route('/print', methods=['POST'])
def vpc_print():
    data = request.json
    success = print_and_ack(data['id'], data['title'])
    if success:
        return jsonify({"status": "success"})
    return jsonify({"error": "Print failed"}), 500

def run_flask():
    # Cloudflared routes VPC traffic to 8080
    app.run(host='0.0.0.0', port=8080, use_reloader=False)


# ==========================================
# TIER 2: WebSocket Subscriber (Real-time Fallback)
# ==========================================
def on_ws_message(ws, message):
    data = json.loads(message)
    logging.info(f"[WS] Received job: {data['id']}")
    print_and_ack(data['id'], data['title'])

def on_ws_error(ws, error):
    logging.error(f"[WS] Error: {error}")

def on_ws_close(ws, close_status_code, close_msg):
    logging.warning("[WS] Disconnected. Reconnecting in 5s...")
    time.sleep(5)
    run_websocket()

def run_websocket():
    ws = websocket.WebSocketApp(WS_URL,
                                on_message=on_ws_message,
                                on_error=on_ws_error,
                                on_close=on_ws_close)
    ws.run_forever()


# ==========================================
# TIER 3: REST Polling (Network Recovery)
# ==========================================
def run_rest_polling():
    while True:
        try:
            res = requests.get(f"{WORKER_URL}/api/printer/pending", timeout=10)
            if res.status_code == 200:
                jobs = res.json()
                for job in jobs:
                    logging.info(f"[POLL] Found missed job: {job['id']}")
                    print_and_ack(job['id'], job['title'])
        except Exception as e:
            pass # Ignore connection errors in the polling loop
        
        time.sleep(15) # Poll every 15 seconds

if __name__ == '__main__':
    logging.info("Starting Dopamine Hardware Bridge (VPC, WS, REST)")
    
    # Start WebSockets in a background thread
    threading.Thread(target=run_websocket, daemon=True).start()
    
    # Start REST Polling in a background thread
    threading.Thread(target=run_rest_polling, daemon=True).start()
    
    # Run Flask on the main thread
    run_flask()
