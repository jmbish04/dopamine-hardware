import logging
import json
import time
import wave
import struct
import math
import threading
import requests
import websocket
import sqlite3
import subprocess
import os
import socket
import evdev
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


# --- 1. Audio Synthesis ---
def generate_sounds():
    """Synthesizes complex 16-bit melodies for UI feedback."""
    def make_melody(filename, notes):
        if os.path.exists(filename): return
        sample_rate = 44100
        with wave.open(filename, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            for freq, duration in notes:
                # Play the note for 85% of the duration, and silence for 15% 
                # This creates that distinct "staccato" separation between notes
                note_samples = int(sample_rate * (duration * 0.85))
                rest_samples = int(sample_rate * (duration * 0.15))
                
                for i in range(note_samples):
                    val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                    f.writeframesraw(struct.pack('<h', val))
                for i in range(rest_samples):
                    f.writeframesraw(struct.pack('<h', 0))

    # 1. PLAY: A quick, ascending double-chime (Booting up)
    make_melody('started.wav', [(440.0, 0.1), (659.25, 0.2)]) # A4 -> E5
    
    # 2. PAUSE: A descending double-chime (Powering down)
    make_melody('paused.wav', [(659.25, 0.1), (440.0, 0.2)])  # E5 -> A4
    
    # 3. DONE: The Antigravity "Dah Dah Dah DAAHHH" Success Fanfare
    make_melody('done.wav', [
        (523.25, 0.15), 
        (523.25, 0.15), 
        (523.25, 0.15), 
        (880.00, 0.5)
    ])        
    
    # 4. ERROR: Two harsh, low buzzes
    make_melody('error.wav', [(150.0, 0.2), (150.0, 0.3)])        

generate_sounds()

def play_sound(action_type):
    """Plays the specific sound without blocking the thread, ignoring missing hardware errors."""
    files = {
        "play": "started.wav",
        "pause": "paused.wav",
        "done": "done.wav",
        "error": "error.wav"
    }
    file = files.get(action_type, "started.wav")
    # Force audio through Card 3 (Logitech USB) using the plughw translator
    subprocess.Popen(['aplay', '-D', 'plughw:3,0', '-q', file], stderr=subprocess.DEVNULL)


# --- 2. Hardware Printing Logic ---
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID)
    except Exception as e:
        logging.error(f"USB Printer error: {repr(e)}")
        return None

def print_and_ack(job_id, title, short_id=None):
    if job_id in printed_jobs: return True
    
    # Fallback if Cloudflare didn't send a short ID
    if not short_id:
        short_id = job_id 
        
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
            p.text(f"ID: {short_id}\n")
            p.set(bold=True)
            p.text(f"{title}\n\n")
            p.set(bold=False)
            
            p.set(align='center')
            # 1D Barcode Logic: {{B forces Character Subset B to allow alphanumeric text
            p.barcode(f"{{B{short_id}", "CODE128", height=80, width=3, pos="BELOW")
            p.text("\n\n\n")
            
            p.cut()
            p.close()
            
            printed_jobs.add(job_id)
            logging.info(f"✅ Printed task: {short_id}")
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id}, timeout=5)
            return True
        except Exception as e:
            logging.error(f"Print hardware failed: {e}")
            if p: p.close()
            return False


# --- 3. Barcode Scanner Thread (Tera D5100) ---
def scanner_worker():
    """Listens globally for USB barcode scanner keystrokes"""
    logging.info("🔍 Searching for USB Barcode Scanner...")
    time.sleep(3) 
    
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    scanner = next((d for d in devices if "keyboard" in d.name.lower() or "scanner" in d.name.lower() or "tera" in d.name.lower() or "usb adapter" in d.name.lower()), None)
            
    if not scanner:
        logging.error("❌ Barcode scanner not found. Retrying in 30s...")
        time.sleep(30)
        return scanner_worker()
        
    logging.info(f"✅ Scanner connected: {scanner.name}")
    buffer = ""
    
    try:
        scanner.grab()
        for event in scanner.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                data = evdev.categorize(event)
                if data.keystate == 1:  # Key Down Event
                    keycode = str(data.keycode).replace('KEY_', '')
                    
                    if keycode == 'ENTER':
                        if len(buffer) > 0:
                            logging.info(f"📠 Barcode Scanned: {buffer}")
                            
                            # Trigger the distinct audio cue based on the command
                            if "PLAY" in buffer:
                                play_sound("play")
                            elif "PAUS" in buffer:
                                play_sound("pause")
                            elif "DONE" in buffer:
                                play_sound("done")
                            else:
                                play_sound("play") # Default for regular task scans
                            
                            # Push the scan to the Cloudflare Worker
                            try:
                                requests.post(
                                    f"{WORKER_URL}/api/printer/scan", 
                                    json={"scanned_code": buffer}, 
                                    timeout=5
                                )
                            except Exception as e:
                                play_sound("error")
                                logging.error(f"Failed to report scan: {e}")
                            buffer = ""
                    # Handle Shift combinations (like the colon in CMD: or dashes in TSK-)
                    elif keycode == 'SEMICOLON':
                        buffer += ':'
                    elif keycode == 'MINUS':
                        buffer += '-'
                    elif len(keycode) == 1:
                        buffer += keycode
    except Exception as e:
        logging.error(f"⚠️ Scanner disconnected: {e}")
        time.sleep(5)
        scanner_worker()


# --- VPC Endpoints ---
@app.route('/print', methods=['POST'])
def vpc_print():
    data = request.json
    if print_and_ack(data['id'], data['title'], data.get('receiptQrValue')):
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
                p.barcode("{BDIAG-OK", "CODE128", height=60, width=2, pos="BELOW")
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
        logging.info(f"⚡ [WS] Received job: {data.get('receiptQrValue', data['id'])}")
        print_and_ack(data['id'], data.get('title', 'Unknown Task'), data.get('receiptQrValue'))
    def on_error(ws, error): pass
    def on_close(ws, close_status_code, close_msg):
        logging.warning("⚠️ [WS] Disconnected. Reconnecting in 5s...")
        time.sleep(5)
        run_websocket()
    ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever(ping_interval=30, ping_timeout=10)

def run_rest_polling():
    while True:
        try:
            res = requests.get(f"{WORKER_URL}/api/printer/pending", timeout=10)
            if res.status_code == 200:
                for job in res.json():
                    logging.info(f"🔄 [POLL] Found missed job: {job.get('receiptQrValue', job['id'])}")
                    print_and_ack(job['id'], job.get('title', 'Unknown Task'), job.get('receiptQrValue'))
        except Exception:
            pass
        time.sleep(15)

if __name__ == '__main__':
    logging.info("🚀 Starting Dopamine Hardware Bridge")
    threading.Thread(target=scanner_worker, daemon=True).start()
    threading.Thread(target=run_websocket, daemon=True).start()
    threading.Thread(target=run_rest_polling, daemon=True).start()
    run_flask()
