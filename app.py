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
# Replace with your actual Worker domain once deployed
WORKER_URL = "https://dopamine.hacolby.workers.dev" 
WS_URL = "wss://dopamine.hacolby.workers.dev/api/printer/ws"

# State lock to prevent duplicate printing across the 3 tiers
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID, profile="TM-T20III")
    except Exception as e:
        logging.error(f"Printer error: {e}")
        return None

def print_and_ack(job_id, title):
    """Core print logic. Safely shared by VPC, WS, and REST threads."""
    if job_id in printed_jobs:
        return True
        
    with printer_lock:
        if job_id in printed_jobs: 
            return True # Double check inside lock
            
        p = get_printer()
        if not p:
            return False

        try:
            p.hw("INIT")
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("THE ONION TASKER\n")
            p.set(align='center', font='a', width=1, height=1, bold=False)
            p.text("-" * 32 + "\n\n")
            
            p.set(align='left')
            p.text(f"ID: {job_id}\n")
            p.set(bold=True)
            p.text(f"{title}\n\n")
            p.set(bold=False)
            
            p.set(align='center')
            p.qr(job_id, size=8, native=True)
            p.text("\n\n\n")
            p.cut()
            p.close()
            
            printed_jobs.add(job_id)
            logging.info(f"✅ Printed task: {job_id}")
            
            # Acknowledge to the Worker so it marks it 'printed' in D1
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id}, timeout=5)
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
    if print_and_ack(data['id'], data['title']):
        return jsonify({"status": "success"})
    return jsonify({"error": "Print failed"}), 500

def run_flask():
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

# ==========================================
# TIER 2: WebSocket Subscriber (Real-time)
# ==========================================
def run_websocket():
    def on_message(ws, message):
        data = json.loads(message)
        logging.info(f"⚡ [WS] Received job: {data['id']}")
        print_and_ack(data['id'], data['title'])

    def on_error(ws, error):
        pass

    def on_close(ws, close_status_code, close_msg):
        logging.warning("⚠️ [WS] Disconnected. Reconnecting in 5s...")
        time.sleep(5)
        run_websocket()

    ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_close=on_close)
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
                    logging.info(f"🔄 [POLL] Found missed job: {job['id']}")
                    print_and_ack(job['id'], job['title'])
        except Exception:
            pass # Fail silently, try again in 15 seconds
        time.sleep(15)

# ==========================================
# TIER 4: Unit Testing
# ==========================================
@app.route('/test', methods=['POST', 'GET'])
def trigger_full_test():
    """
    Diagnostic endpoint. The Cloudflare Worker calls this via VPC to demand a hardware test.
    """
    logging.info("🛠️ Diagnostic test triggered via VPC")
    
    report = {
        "status": "healthy",
        "printer": "unknown",
        "network": "unknown",
        "timestamp": time.time()
    }
    
    # 1. Test Printer Hardware
    with printer_lock:
        p = get_printer()
        if p:
            try:
                p.hw("INIT")
                p.set(align='center', font='a', width=2, height=2, bold=True)
                p.text("DIAGNOSTIC TEST\n")
                p.set(align='center', font='a', width=1, height=1, bold=False)
                p.text("-" * 32 + "\n\n")
                
                # Get local IP for debugging
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()

                p.set(align='left')
                p.text(f"IP: {local_ip}\n")
                p.text("VPC: ACTIVE\n")
                p.text("STATUS: ALL SYSTEMS GO\n\n")
                
                p.set(align='center')
                p.qr("DIAGNOSTIC-OK", size=6, native=True)
                p.text("\n\n\n")
                p.cut()
                p.close()
                report["printer"] = "online"
            except Exception as e:
                logging.error(f"Diagnostic print failed: {e}")
                report["printer"] = f"error: {str(e)}"
                report["status"] = "degraded"
        else:
            report["printer"] = "disconnected"
            report["status"] = "degraded"

    # 2. Return report to Cloudflare Worker
    return jsonify(report), 200 if report["status"] == "healthy" else 503

if __name__ == '__main__':
    logging.info("Starting Dopamine Hardware Bridge (VPC + WS + REST)")
    
    # Start fallbacks in background threads
    threading.Thread(target=run_websocket, daemon=True).start()
    threading.Thread(target=run_rest_polling, daemon=True).start()
    
    # Run the VPC listener on the main thread
    run_flask()
