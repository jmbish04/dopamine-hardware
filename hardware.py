# hardware.py
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
import worker_ai
from datetime import datetime
from escpos.printer import Usb
from config import VENDOR_ID, PRODUCT_ID, WORKER_URL

# --- Audio Engine ---
audio_lock = threading.Lock()

def play_audio_file(audio_path):
    """Plays an audio file using mpg123 (for mp3) or aplay (for wav)."""
    try:
        if audio_path.lower().endswith('.mp3'):
            cmd = ["mpg123", "-q", audio_path]
        else:
            cmd = ["aplay", "-D", "plughw:3,0", "-q", audio_path]

        with audio_lock:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        return True
    except FileNotFoundError:
        missing_bin = "mpg123" if audio_path.lower().endswith('.mp3') else "aplay"
        logging.warning(f"'{missing_bin}' not found - run 'sudo apt-get install {missing_bin} -y'")
        return False
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore').strip() if e.stderr else str(e)
        logging.error(f"Failed to play audio ({cmd[0]} error): {error_msg}")
        return False
    except subprocess.TimeoutExpired:
        logging.error("Audio playback timed out")
        return False
    except Exception as e:
        logging.error(f"Failed to play audio: {e}")
        return False

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
                note_samples = int(sample_rate * (duration * 0.85))
                rest_samples = int(sample_rate * (duration * 0.15))
                for i in range(note_samples):
                    val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                    f.writeframesraw(struct.pack('<h', val))
                for i in range(rest_samples):
                    f.writeframesraw(struct.pack('<h', 0))

    make_melody('started.wav', [(440.0, 0.1), (659.25, 0.2)]) 
    make_melody('paused.wav', [(659.25, 0.1), (440.0, 0.2)])  
    make_melody('done.wav', [(523.25, 0.15), (523.25, 0.15), (523.25, 0.15), (880.00, 0.5)])
    make_melody('error.wav', [(150.0, 0.2), (150.0, 0.3)])

generate_sounds()

def play_sound(action_type):
    """Plays the specific sound utilizing the thread-safe audio engine."""
    files = {
        "play": "started.wav",
        "pause": "paused.wav",
        "done": "done.wav",
        "error": "error.wav"
    }
    file = files.get(action_type, "started.wav")
    def _play():
        play_audio_file(file)
    threading.Thread(target=_play, daemon=True).start()

# --- Printer Logic ---
printed_jobs = set()
printer_lock = threading.Lock()

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID, profile="TM-T20III")
    except Exception as e:
        logging.error(f"USB Printer error: {repr(e)}")
        return None

def _sanitize_escpos_input(text):
    if not text:
        return ""
    text = ''.join(char for char in text if ord(char) < 128 and (32 <= ord(char) <= 126 or ord(char) in (9, 10)))
    text = re.sub(r'\x1b.', '', text)
    return text[:512]

def _format_timestamp(timestamp):
    if not timestamp:
        return ""
    try:
        if isinstance(timestamp, (int, float)):
            if timestamp > 10000000000:
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        elif isinstance(timestamp, str):
            if 'T' in timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d %H:%M")
            return timestamp
    except Exception:
        return str(timestamp)
    return str(timestamp)

def print_and_ack(data):
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
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("DOPAMINE\n")
            p.set(align='center', font='a', width=1, height=1, bold=False)
            p.text("-" * 32 + "\n\n")

            p.set(align='left', font='a', bold=False)
            printed_fields = set()

            task_id = data.get('taskId') or data.get('receiptQrValue') or job_id
            task_id_clean = _sanitize_escpos_input(str(task_id))
            p.set(bold=True)
            p.text(f"Task ID: {task_id_clean}\n")
            p.set(bold=False)
            printed_fields.update(['taskId', 'receiptQrValue', 'id'])

            title = data.get('title')
            title_clean = ""
            if title:
                title_clean = _sanitize_escpos_input(str(title))
                p.text(f"Title: {title_clean}\n")
                printed_fields.add('title')

            if data.get('description'):
                desc_clean = _sanitize_escpos_input(str(data['description']))
                p.text(f"Description: {desc_clean}\n")
                printed_fields.add('description')

            if data.get('status'):
                status_clean = _sanitize_escpos_input(str(data['status']))
                p.text(f"Status: {status_clean}\n")
                printed_fields.add('status')

            if data.get('dueDate'):
                due_date_formatted = _format_timestamp(data['dueDate'])
                due_date_clean = _sanitize_escpos_input(due_date_formatted)
                p.text(f"Due: {due_date_clean}\n")
                printed_fields.add('dueDate')

            if data.get('createdAt'):
                created_formatted = _format_timestamp(data['createdAt'])
                created_clean = _sanitize_escpos_input(created_formatted)
                p.text(f"Created: {created_clean}\n")
                printed_fields.add('createdAt')

            remaining_fields = {k: v for k, v in data.items() if k not in printed_fields and v is not None}
            if remaining_fields:
                p.text("\n")
                for key, value in sorted(remaining_fields.items()):
                    key_formatted = re.sub(r'([A-Z])', r' \1', key).title().strip()
                    value_str = str(value)
                    if 'date' in key.lower() or 'time' in key.lower() or key.lower().endswith('at'):
                        value_str = _format_timestamp(value)
                    value_clean = _sanitize_escpos_input(value_str)[:100]
                    p.text(f"{key_formatted}: {value_clean}\n")

            p.text("\n")
            p.set(align='center')
            safe_barcode = ''.join(c for c in task_id_clean if c.isalnum() or c in '-_')[:48]
            if safe_barcode:
                p.barcode(f"{{B{safe_barcode}", "CODE128", height=80, width=3, pos="BELOW")
            p.text("\n\n\n")

            p.cut()
            p.close()

            printed_jobs.add(job_id)
            logging.info(f"✅ Printed task: {task_id_clean}")
            
            # Announce the new task via thread
            if title_clean:
                def announce():
                    path = worker_ai.generate_announcement_audio(title_clean)
                    if path:
                        play_audio_file(path)
                        try: os.remove(path)
                        except OSError: pass
                threading.Thread(target=announce, daemon=True).start()

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
    while True:
        try:
            logging.info("🔍 Searching for USB Barcode Scanner...")
            time.sleep(3)

            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            scanner = next((d for d in devices if "keyboard" in d.name.lower() or "scanner" in d.name.lower() or "tera" in d.name.lower() or "usb adapter" in d.name.lower()), None)

            if not scanner:
                logging.error("❌ Barcode scanner not found. Retrying in 30s...")
                time.sleep(30)
                continue

            logging.info(f"✅ Scanner connected: {scanner.name}")
            buffer = ""

            try:
                scanner.grab()
                for event in scanner.read_loop():
                    if event.type == evdev.ecodes.EV_KEY:
                        data = evdev.categorize(event)
                        if data.keystate == 1:
                            keycode = str(data.keycode).replace('KEY_', '')

                            if keycode == 'ENTER':
                                if len(buffer) > 0:
                                    logging.info(f"📠 Barcode Scanned: {buffer}")

                                    if "PLAY" in buffer:
                                        action_type = "resumed"
                                        sound_type = "play"
                                    elif "PAUS" in buffer:
                                        action_type = "paused"
                                        sound_type = "pause"
                                    elif "DONE" in buffer:
                                        action_type = "completed"
                                        sound_type = "done"
                                    else:
                                        action_type = "scanned"
                                        sound_type = "play"

                                    play_sound(sound_type)

                                    try:
                                        res = requests.post(
                                            f"{WORKER_URL}/api/printer/scan",
                                            json={"scanned_code": buffer},
                                            timeout=5
                                        )
                                        task_title = "The task"
                                        if res.status_code == 200:
                                            try:
                                                resp_json = res.json()
                                                if "title" in resp_json:
                                                    task_title = resp_json["title"]
                                            except Exception:
                                                pass
                                                
                                        def play_feedback():
                                            audio_paths = worker_ai.generate_multi_speaker_task_audio(task_title, action_type)
                                            for p in audio_paths:
                                                play_audio_file(p)
                                                try: os.remove(p)
                                                except OSError: pass

                                        threading.Thread(target=play_feedback, daemon=True).start()
                                        
                                    except Exception as e:
                                        play_sound("error")
                                        logging.error(f"Failed to report scan: {e}")
                                    buffer = ""
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
        except Exception as e:
            logging.error(f"Scanner worker error: {e}")
            time.sleep(5)
