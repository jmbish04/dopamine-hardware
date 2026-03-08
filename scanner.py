"""
Barcode scanner (Tera D5100) interface via evdev.
Listens for USB HID keyboard events and reports scans to the Cloudflare Worker.
"""
import logging
import time
import requests
import evdev
from config import WORKER_URL
from audio import play_sound

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
