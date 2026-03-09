import logging
import threading
from core_logger import setup_logger
from telemetry import telemetry_worker
from scanner import scanner_worker
from cloud_sync import run_websocket, run_rest_polling
from api import app

def main():
    """
    Main entry point for the Dopamine Hardware Bridge.

    For production deployment, use Gunicorn instead of Flask's dev server:
        gunicorn --workers 3 --bind 0.0.0.0:8080 main:app --timeout 120

    Or update dopamine.service to use Gunicorn directly.
    """
    setup_logger()
    logging.info("🚀 Starting Dopamine Hardware Bridge (Modularized)")

    # Start background worker threads
    threading.Thread(target=telemetry_worker, daemon=True).start()
    threading.Thread(target=scanner_worker, daemon=True).start()
    threading.Thread(target=run_websocket, daemon=True).start()
    threading.Thread(target=run_rest_polling, daemon=True).start()

    # Flask dev server (use Gunicorn in production)
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

if __name__ == '__main__':
    main()
