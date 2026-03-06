import logging
import time
import threading
import requests
import evdev
import wave
import struct
import math
import subprocess
import os
from escpos.printer import Usb
from config import VENDOR_ID, PRODUCT_ID, WORKER_URL

# --- Audio Synthesis ---
def generate_sounds():
    """Synthesizes local beep sounds so no external files are needed."""
    def make_wav(filename, freq, duration):
        if os.path.exists(filename): return
        sample_rate = 44100
        with wave.open(filename, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            for i in range(int(sample_rate * duration)):
                val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                f.writeframesraw(struct.pack('<h', val))

    make_wav('task_beep.wav', 880, 0.1)      # High short beep (Task Scan)
    make_wav('action_beep.wav', 523, 0.15)  # Lower longer beep (Action Scan)
    make_wav('error_beep.wav', 150, 0.3)    # Low buzz (Error)

generate_sounds()

def play_sound(sound_type):
    """Plays sound without blocking the thread"""
    file = "task_beep.wav" if sound_type == "task" else "action_beep.wav"
    if sound_type == "error": file = "error_beep.wav"
    subprocess.Popen(['aplay', '-q', file])

# --- Printer Logic ---
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        # Removed the profile="TM-T20III" argument to prevent the KeyError
        return Usb(VENDOR_ID, PRODUCT_ID)
    except Exception as e:
        logging.error(f"USB Printer error: {repr(e)}")
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

# --- Scanner Logic ---
def scanner_worker():
    """Listens globally for USB barcode scanner keystrokes"""
    logging.info("🔍 Searching for USB Barcode Scanner...")
    time.sleep(3)

    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    scanner = next((d for d in devices if "keyboard" in d.name.lower() or "scanner" in d.name.lower() or "tera" in d.name.lower() or "sycreader" in d.name.lower() or "hid" in d.name.lower()), None)

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

                            if buffer.startswith("CMD:"):
                                play_sound("action")
                            else:
                                play_sound("task")

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
                    elif keycode == 'SEMICOLON':
                        buffer += ':'
                    elif len(keycode) == 1:
                        buffer += keycode
    except Exception as e:
        logging.error(f"⚠️ Scanner disconnected: {e}")
        try:
            scanner.ungrab()
        except:
            pass
        time.sleep(5)
        scanner_worker()
