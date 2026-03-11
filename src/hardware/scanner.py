"""
Barcode scanner (Tera D5100) interface via evdev.
Listens for USB HID keyboard events and reports scans to the Cloudflare Worker.
"""
import logging
import time
import requests
import evdev
import threading
from src.core.config import WORKER_URL
from src.hardware.audio import play_sound, play_audio_file

def _sanitize_task_name(text):
    """Sanitize task name to prevent prompt injection attacks in AI audio generation."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    # Remove control characters, newlines, and potential prompt injection patterns
    # Keep only printable ASCII and basic punctuation
    text = ''.join(char for char in text if 32 <= ord(char) <= 126)
    # Remove quotes that could break out of prompt context
    text = text.replace('"', '').replace("'", '')
    # Limit length to prevent prompt stuffing
    return text[:100]

def _play_multi_speaker_audio_async(task_name, action):
    """
    Asynchronously generate and play multi-speaker task completion audio.
    This runs in a separate thread to avoid blocking the scanner.
    """
    try:
        # Import here to avoid circular dependency issues
        import src.ai as ai

        # Generate two audio files: male confirmation + female motivation
        audio_paths = ai.generate_multi_speaker_task_audio(task_name, action)

        # Play each audio file sequentially
        for audio_path in audio_paths:
            if audio_path:
                play_audio_file(audio_path)

    except Exception as e:
        logging.error(f"Failed to generate/play multi-speaker audio: {e}")

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

                                    # Determine action type from buffer
                                    action = None
                                    if "PLAY" in buffer:
                                        play_sound("play")
                                        action = "started"
                                    elif "PAUS" in buffer:
                                        play_sound("pause")
                                        action = "paused"
                                    elif "DONE" in buffer:
                                        play_sound("done")
                                        action = "completed"
                                    else:
                                        play_sound("play") # Default for regular task scans

                                    # Push the scan to the Cloudflare Worker and get task info
                                    try:
                                        response = requests.post(
                                            f"{WORKER_URL}/api/printer/scan",
                                            json={"scanned_code": buffer},
                                            timeout=5
                                        )

                                        # If this was a task action (complete/pause/start) and we got task info back,
                                        # trigger multi-speaker audio feedback asynchronously
                                        if action and response.status_code == 200:
                                            try:
                                                response_data = response.json()
                                                # Extract nested task object from API response
                                                task_data = response_data.get('task') or {}
                                                # Check nested task.title, root title, nested task.taskId, root taskId
                                                task_name = task_data.get('title') or response_data.get('title') or task_data.get('taskId') or response_data.get('taskId') or 'Unknown Task'
                                                # Sanitize task name to prevent prompt injection attacks
                                                task_name = _sanitize_task_name(task_name)

                                                # Start audio generation/playback in background thread
                                                audio_thread = threading.Thread(
                                                    target=_play_multi_speaker_audio_async,
                                                    args=(task_name, action),
                                                    daemon=True
                                                )
                                                audio_thread.start()
                                            except Exception as e:
                                                logging.warning(f"Could not trigger multi-speaker audio: {e}")

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
