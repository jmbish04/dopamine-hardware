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
import re
from datetime import datetime
from escpos.printer import Usb
from config import VENDOR_ID, PRODUCT_ID, WORKER_URL

# --- Audio Synthesis ---
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

# --- Printer Logic ---
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID)
    except Exception as e:
        logging.error(f"USB Printer error: {repr(e)}")
        return None

def _sanitize_escpos_input(text):
    """Remove or escape potentially dangerous ESC/POS control sequences and strip emoji."""
    if not text:
        return ""

    # Remove emoji and other non-ASCII characters that printer can't handle
    # Keep only printable ASCII characters (32-126) plus newline (10) and tab (9)
    text = ''.join(char for char in text if ord(char) < 128 and (32 <= ord(char) <= 126 or ord(char) in (9, 10)))

    # Remove ESC/POS control sequences (ESC followed by any character)
    text = re.sub(r'\x1b.', '', text)

    # Limit length to prevent abuse
    return text[:512]

def _format_timestamp(timestamp):
    """Format a Unix timestamp or ISO string to readable date."""
    if not timestamp:
        return ""

    try:
        # Try parsing as Unix timestamp (seconds or milliseconds)
        if isinstance(timestamp, (int, float)):
            if timestamp > 10000000000:  # Milliseconds
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        # Try parsing as ISO string
        elif isinstance(timestamp, str):
            # Handle ISO format
            if 'T' in timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d %H:%M")
            return timestamp
    except Exception:
        return str(timestamp)

    return str(timestamp)

def print_and_ack(data):
    """
    Print a task receipt with all available data.

    Args:
        data: Dictionary containing task information. Expected fields:
            - id (required): Job ID for tracking
            - taskId: Task identifier
            - title: Task title
            - description: Task description
            - dueDate: Due date timestamp
            - status: Task status
            - createdAt: Creation timestamp
            - receiptQrValue: Short ID for barcode
            - Any other fields will be printed as key:value
    """
    job_id = data.get('id')
    if not job_id:
        logging.error("print_and_ack called without job ID")
        return False

    if job_id in printed_jobs:
        return True

    with printer_lock:
        if job_id in printed_jobs:
            return True
        p = get_printer()
        if not p:
            return False
        try:
            p.hw("INIT")

            # Header
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("DOPAMINE\n")
            p.set(align='center', font='a', width=1, height=1, bold=False)
            p.text("-" * 32 + "\n\n")

            # Well-known fields in specific order
            p.set(align='left', font='a', bold=False)

            # Track which fields we've already printed
            printed_fields = set()

            # Print taskId if available
            task_id = data.get('taskId') or data.get('receiptQrValue') or job_id
            task_id_clean = _sanitize_escpos_input(str(task_id))
            p.set(bold=True)
            p.text(f"Task ID: {task_id_clean}\n")
            p.set(bold=False)
            printed_fields.update(['taskId', 'receiptQrValue', 'id'])

            # Print title
            if data.get('title'):
                title_clean = _sanitize_escpos_input(str(data['title']))
                p.text(f"Title: {title_clean}\n")
                printed_fields.add('title')

            # Print description (allow multiline)
            if data.get('description'):
                desc_clean = _sanitize_escpos_input(str(data['description']))
                p.text(f"Description: {desc_clean}\n")
                printed_fields.add('description')

            # Print status
            if data.get('status'):
                status_clean = _sanitize_escpos_input(str(data['status']))
                p.text(f"Status: {status_clean}\n")
                printed_fields.add('status')

            # Print due date
            if data.get('dueDate'):
                due_date_formatted = _format_timestamp(data['dueDate'])
                due_date_clean = _sanitize_escpos_input(due_date_formatted)
                p.text(f"Due: {due_date_clean}\n")
                printed_fields.add('dueDate')

            # Print created at
            if data.get('createdAt'):
                created_formatted = _format_timestamp(data['createdAt'])
                created_clean = _sanitize_escpos_input(created_formatted)
                p.text(f"Created: {created_clean}\n")
                printed_fields.add('createdAt')

            # Print any remaining fields
            remaining_fields = {k: v for k, v in data.items() if k not in printed_fields and v is not None}
            if remaining_fields:
                p.text("\n")
                for key, value in sorted(remaining_fields.items()):
                    # Format key nicely (camelCase to Title Case)
                    key_formatted = re.sub(r'([A-Z])', r' \1', key).title().strip()
                    value_str = str(value)
                    # Handle timestamps
                    if 'date' in key.lower() or 'time' in key.lower() or key.lower().endswith('at'):
                        value_str = _format_timestamp(value)
                    value_clean = _sanitize_escpos_input(value_str)[:100]  # Limit value length
                    p.text(f"{key_formatted}: {value_clean}\n")

            # Barcode
            p.text("\n")
            p.set(align='center')
            # 1D Barcode Logic: {{B forces Character Subset B to allow alphanumeric text
            safe_barcode = ''.join(c for c in task_id_clean if c.isalnum() or c in '-_')[:48]
            if safe_barcode:
                p.barcode(f"{{B{safe_barcode}", "CODE128", height=80, width=3, pos="BELOW")
            p.text("\n\n\n")

            p.cut()
            p.close()

            printed_jobs.add(job_id)
            logging.info(f"✅ Printed task: {task_id_clean}")
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id}, timeout=5)
            return True
        except Exception as e:
            logging.error(f"Print hardware failed: {e}")
            if p:
                p.close()
            return False

# --- Scanner Logic ---
def scanner_worker():
    """Listens globally for USB barcode scanner keystrokes"""
    while True:  # Use iterative loop instead of recursion
        try:
            logging.info("🔍 Searching for USB Barcode Scanner...")
            time.sleep(3)

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            scanner = next((d for d in devices if "keyboard" in d.name.lower() or "scanner" in d.name.lower() or "tera" in d.name.lower() or "usb adapter" in d.name.lower()), None)

            if not scanner:
                logging.error("❌ Barcode scanner not found. Retrying in 30s...")
                time.sleep(30)
                continue  # Retry in the loop

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
                try:
                    scanner.ungrab()
                except Exception as ungrab_error:
                    logging.warning(f"Failed to ungrab scanner: {ungrab_error}")
                time.sleep(5)
                # Loop will retry connection
        except Exception as e:
            logging.error(f"Scanner worker error: {e}")
            time.sleep(5)
