"""
Main entry point for the Dopamine Hardware Bridge (Modularized).

This script initializes the hardware bridge with the following components:
- Telemetry worker: Logs to local SQLite DB and Cloudflare Worker
- Scanner worker: Monitors barcode scanner input
- WebSocket worker: Maintains persistent connection to Cloudflare Worker
- REST polling worker: Fallback mechanism for missed jobs
- Flask API server: HTTP endpoints exposed via Cloudflare Tunnel

For production deployment, use Gunicorn instead of Flask's dev server:
    gunicorn --workers 3 --bind 0.0.0.0:8080 main:app --timeout 120

Or update dopamine.service to use Gunicorn directly.
"""
import logging
import threading
from src.core.core_logger import setup_logger
from src.core.telemetry import telemetry_worker
from src.hardware.scanner import scanner_worker
from src.network.cloud_sync import run_websocket, run_rest_polling
from src.api.api import app

def main():
    """Main entry point for the Dopamine Hardware Bridge."""
    setup_logger()
    logging.info("🚀 Starting Dopamine Hardware Bridge (Modularized v2)")

    # Start background worker threads
    threading.Thread(target=telemetry_worker, daemon=True, name="TelemetryWorker").start()
    threading.Thread(target=scanner_worker, daemon=True, name="ScannerWorker").start()
    threading.Thread(target=run_websocket, daemon=True, name="WebSocketWorker").start()
    threading.Thread(target=run_rest_polling, daemon=True, name="RESTPollingWorker").start()

    # Flask dev server (use Gunicorn in production)
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

if __name__ == '__main__':
    main()
