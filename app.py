import logging
import json
import time
import threading
import requests
import websocket
import sqlite3
import subprocess
import socket
import evdev  # <-- New Import
from queue import Queue
from flask import Flask, request, jsonify
from escpos.printer import Usb

app = Flask(__name__)

# --- Configuration ---
VENDOR_ID = 0x04b8
PRODUCT_ID = 0x0e28
WORKER_URL = "https://dopamine.hacolby.workers.dev" 
WS_URL = "wss://dopamine.hacolby.workers.dev/api/printer/ws"

log_queue = Queue()

def telemetry_worker():
    conn = sqlite3.connect('/home/pi/dopamine-hardware/dopamine_logs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS system_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp REAL,
                  level TEXT,
                  message TEXT)''')
    conn.commit()

    while True:
        log_entry = log_queue.get()
        if log_entry is None: break
        
        c.execute("INSERT INTO system_logs (timestamp, level, message) VALUES (?, ?, ?)",
                  (log_entry['timestamp'], log_entry['level'], log_entry['message']))
        conn.commit()

        try:
            cf_payload = {
                "timestamp": log_entry['timestamp'],
                "status": log_entry['level'],      
                "printer": log_entry['message'],   
                "network": "vpc-tunnel"
            }
            requests.post(f"{WORKER_URL}/api/printer/telemetry", json=cf_payload, timeout=3)
        except Exception:
            pass

class DualLoggerHandler(logging.Handler):
    def emit(self, record):
        log_queue.put({
            "timestamp": time.time(),
            "level": record.levelname,
            "message": self.format(record)
        })

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

dual_handler = DualLoggerHandler()
dual_handler.setFormatter(formatter)
logger.addHandler(dual_handler)

logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

threading.Thread(target=telemetry_worker, daemon=True).start()

# --- Hardware Logic ---
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID, profile="TM-T20III")
    except Exception as e:
        logging.error(f"USB Printer error: {e}")
        return None

def print_and_ack(job_id, title):
    if job_id in printed_jobs: return True
    with printer_lock:
        if job_id in printed_jobs: return True
        p = get_printer()
        if not p: return False
        try:
            p.hw("INIT")
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("ONION TASKER\n")
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
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id}, timeout=5)
            return True
        except Exception as e:
            logging.error(f"Print hardware failed: {e}")
            if p: p.close()
            return False

# ==========================================
# NEW: Barcode Scanner Thread (Tera D5100)
# ==========================================
def scanner_worker():
    """Listens globally for USB barcode scanner keystrokes"""
    logging.info("🔍 Searching for USB Barcode Scanner...")
    
    # Give the OS a moment to enumerate USB devices on boot
    time.sleep(3) 
    
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    scanner = None
    for dev in devices:
        name = dev.name.lower()
        # Tera scanners usually register as generic keyboards or scanners
        if "keyboard" in name or "scanner" in name or "tera" in name or "hid" in name:
            scanner = dev
            break
            
    if not scanner:
        logging.error("❌ Barcode scanner not found in /dev/input/. Retrying in 30s...")
        time.sleep(30)
        return scanner_worker()
        
    logging.info(f"✅ Scanner connected: {scanner.name} at {scanner.path}")
    buffer = ""
    
    try:
        # Exclusively grab the scanner so keystrokes don't leak into the Pi's main terminal
        scanner.grab()
        
        for event in scanner.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                data = evdev.categorize(event)
                if data.keystate == 1:  # Key Down Event
                    keycode = str(data.keycode)
                    
                    if keycode == 'KEY_ENTER':
                        if len(buffer) > 0:
                            logging.info(f"📠 Barcode Scanned: {buffer}")
                            # Send the scanned code up to Cloudflare
                            try:
                                requests.post(
                                    f"{WORKER_URL}/api/printer/scan", 
                                    json={"scanned_code": buffer}, 
                                    timeout=5
                                )
                            except Exception as e:
                                logging.error(f"Failed to report scan to Worker: {e}")
                            buffer = ""
                    elif keycode.startswith('KEY_'):
                        # Parse 'KEY_A' -> 'A', 'KEY_1' -> '1'
                        char = keycode.replace('KEY_', '')
                        if len(char) == 1: # Ignore SHIFT, CTRL, etc.
                            buffer += char
    except Exception as e:
        logging.error(f"⚠️ Scanner disconnected or error: {e}")
        try:
            scanner.ungrab()
        except:
            pass
        time.sleep(5)
        scanner_worker() # Loop and attempt to reconnect

# --- VPC Endpoints ---
@app.route('/print', methods=['POST'])
def vpc_print():
    data = request.json
    if print_and_ack(data['id'], data['title']):
        return jsonify({"status": "success"})
    return jsonify({"error": "Print failed"}), 500

@app.route('/test', methods=['POST', 'GET'])
def trigger_full_test():
    logging.info("🛠️ Diagnostic test triggered via VPC")
    report = {"status": "healthy", "printer": "unknown", "network": "unknown", "timestamp": time.time()}
    with printer_lock:
        p = get_printer()
        if p:
            try:
                p.hw("INIT")
                p.set(align='center', font='a', width=2, height=2, bold=True)
                p.text("DIAGNOSTIC TEST\n")
                p.set(align='center', font='a', width=1, height=1, bold=False)
                p.text("-" * 32 + "\n\n")
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                report["network"] = local_ip
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
                report["printer"] = "error"
                report["error"] = str(e)
                report["status"] = "degraded"
        else:
            report["printer"] = "disconnected"
            report["status"] = "degraded"
    return jsonify(report), 200 if report["status"] == "healthy" else 503

@app.route('/logs', methods=['GET'])
def get_system_logs():
    lines = request.args.get('lines', '50')
    try:
        logging.info("VPC requested journalctl logs")
        output = subprocess.check_output(['journalctl', '-u', 'dopamine.service', '-n', str(lines), '--no-pager'], text=True)
        return jsonify({"status": "success", "logs": output})
    except Exception as e:
        logging.error(f"Failed to read journalctl: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

def run_flask():
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

# --- Fallback Connections ---
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

if __name__ == '__main__':
    logging.info("🚀 Starting Dopamine Hardware Bridge")
    threading.Thread(target=scanner_worker, daemon=True).start()
    threading.Thread(target=run_websocket, daemon=True).start()
    threading.Thread(target=run_rest_polling, daemon=True).start()
    run_flask()
