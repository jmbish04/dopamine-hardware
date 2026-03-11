"""
WebSocket and REST polling communication with Cloudflare Worker.
Provides resilient connection with application-level heartbeats and graceful error handling.
"""
import json
import time
import logging
import traceback
import requests
import websocket
import threading
import websocket._exceptions
from src.core.config import WS_URL, WORKER_URL
from src.hardware.printer import print_and_ack

# Track reconnection count for telemetry
reconnection_count = 0

def _sanitize_for_logging(text):
    """Sanitize text for logging to prevent log injection attacks."""
    if not isinstance(text, str):
        text = str(text)
    # Remove newlines, carriage returns, and other control characters
    # Keep only printable ASCII and spaces
    text = ''.join(char for char in text if 32 <= ord(char) <= 126)
    # Limit length to prevent log file exhaustion
    return text[:200]

def run_websocket():
    """
    Maintain WebSocket connection with iterative reconnection logic.

    Implements:
    - Graceful handling of expected Cloudflare connection drops
    - Application-level heartbeat every 45 seconds
    - Automatic reconnection with exponential backoff
    """
    global reconnection_count

    while True:  # Use iterative loop instead of recursion
        # Control flags for heartbeat thread
        stop_heartbeat = threading.Event()
        heartbeat_thread = None
        ws = None

        try:
            def send_heartbeat(ws, stop_event):
                """
                Send application-level heartbeat to keep Cloudflare tunnel alive.
                Runs in background thread.
                """
                while not stop_event.is_set():
                    try:
                        time.sleep(45)  # Send heartbeat every 45 seconds
                        if not stop_event.is_set():
                            heartbeat_msg = json.dumps({
                                "type": "heartbeat",
                                "timestamp": time.time(),
                                "reconnect_count": reconnection_count
                            })
                            ws.send(heartbeat_msg)
                            logging.debug("💓 [WS] Heartbeat sent")
                    except Exception as e:
                        # Silently handle heartbeat failures (connection may be closing)
                        logging.debug(f"[WS] Heartbeat failed: {e}")
                        break

            def on_open(ws):
                """Handle WebSocket connection opened."""
                nonlocal heartbeat_thread, stop_heartbeat
                logging.info(f"✅ [WS] Connected to {WS_URL}")

                # Start heartbeat thread
                stop_heartbeat.clear()
                heartbeat_thread = threading.Thread(
                    target=send_heartbeat,
                    args=(ws, stop_heartbeat),
                    daemon=True
                )
                heartbeat_thread.start()

            def on_message(ws, message):
                """Handle incoming WebSocket messages with comprehensive error handling."""
                try:
                    data = json.loads(message)

                    # Handle heartbeat acknowledgments
                    if data.get('type') == 'heartbeat_ack':
                        logging.debug("💓 [WS] Heartbeat acknowledged")
                        return

                    # Check if this is a print job (has id field) or just an info message
                    if 'id' not in data and 'taskId' not in data:
                        # This is not a print job, just log it and skip
                        # Sanitize the entire data dict for logging to prevent log injection
                        safe_data = _sanitize_for_logging(str(data))
                        logging.debug(f"⚡ [WS] Received non-print message: {safe_data}")
                        return

                    job_id = data.get('receiptQrValue') or data.get('taskId') or data.get('id', 'unknown')
                    # Sanitize job_id to prevent log injection attacks
                    safe_job_id = _sanitize_for_logging(job_id)
                    logging.info(f"⚡ [WS] Received print job: {safe_job_id}")
                    print_and_ack(data)
                except json.JSONDecodeError as e:
                    logging.error(f"⚠️ [WS] Invalid JSON: {e}")
                    logging.debug(traceback.format_exc())
                except Exception as e:
                    logging.error(f"⚠️ [WS] Error processing message: {e}")
                    logging.error(f"⚠️ [WS] Full traceback:\n{traceback.format_exc()}")

            def on_error(ws, error):
                """Handle WebSocket errors with graceful logging for expected disconnects."""
                # Check if this is an expected Cloudflare disconnect
                if isinstance(error, (
                    websocket._exceptions.WebSocketConnectionClosedException,
                    websocket._exceptions.WebSocketTimeoutException,
                    ConnectionResetError
                )):
                    logging.info(f"ℹ️ [WS] Connection closed by remote host (expected): {type(error).__name__}. Reconnecting...")
                else:
                    # Unexpected error - log with more detail
                    logging.warning(f"⚠️ [WS] Unexpected error: {error}")
                    logging.debug(traceback.format_exc())

            def on_close(ws, close_status_code, close_msg):
                """Handle WebSocket connection closed."""
                nonlocal stop_heartbeat, heartbeat_thread

                # Stop heartbeat thread
                if heartbeat_thread and heartbeat_thread.is_alive():
                    stop_heartbeat.set()
                    heartbeat_thread.join(timeout=2)

                logging.info(f"🔌 [WS] Disconnected (status: {close_status_code}). Reconnecting in 5s...")

            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            # Run WebSocket with protocol-level keepalive
            ws.run_forever(ping_interval=30, ping_timeout=10)

            # Increment reconnection counter
            reconnection_count += 1

            # If run_forever returns, wait before reconnecting
            time.sleep(5)

        except websocket._exceptions.WebSocketConnectionClosedException as e:
            # Expected Cloudflare disconnect - graceful handling
            logging.info("ℹ️ [WS] Connection closed by remote host. Reconnecting in 5s...")
            reconnection_count += 1
            time.sleep(5)

        except websocket._exceptions.WebSocketTimeoutException as e:
            # Timeout - expected on Cloudflare
            logging.info("ℹ️ [WS] Connection timeout. Reconnecting in 5s...")
            reconnection_count += 1
            time.sleep(5)

        except ConnectionResetError as e:
            # Connection reset - expected network issue
            logging.info("ℹ️ [WS] Connection reset by peer. Reconnecting in 5s...")
            reconnection_count += 1
            time.sleep(5)

        except Exception as e:
            # Unexpected error
            logging.error(f"⚠️ [WS] Unexpected connection error: {e}. Reconnecting in 5s...")
            logging.debug(traceback.format_exc())
            reconnection_count += 1
            time.sleep(5)

        finally:
            # Ensure heartbeat thread is stopped
            if heartbeat_thread and heartbeat_thread.is_alive():
                stop_heartbeat.set()
                heartbeat_thread.join(timeout=2)

def run_rest_polling():
    """Poll for pending jobs with error logging."""
    while True:
        try:
            res = requests.get(f"{WORKER_URL}/api/printer/pending", timeout=10)
            if res.status_code == 200:
                jobs = res.json()
                for job in jobs:
                    job_id = job.get('receiptQrValue') or job.get('taskId') or job.get('id', 'unknown')
                    # Sanitize job_id to prevent log injection attacks
                    safe_job_id = _sanitize_for_logging(job_id)
                    logging.info(f"🔄 [POLL] Found missed job: {safe_job_id}")
                    print_and_ack(job)
        except requests.exceptions.RequestException as e:
            logging.warning(f"[POLL] Failed to fetch pending jobs: {e}")
        except Exception as e:
            logging.error(f"[POLL] Unexpected error: {e}")
        time.sleep(15)
