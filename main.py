import logging
import threading
from core_logger import setup_logger
from telemetry import telemetry_worker
from hardware import scanner_worker
from cloud_sync import run_websocket, run_rest_polling
from api import app

def main():
    setup_logger()
    logging.info("🚀 Starting Dopamine Hardware Bridge (Modularized)")

    threading.Thread(target=telemetry_worker, daemon=True).start()
    threading.Thread(target=scanner_worker, daemon=True).start()
    threading.Thread(target=run_websocket, daemon=True).start()
    threading.Thread(target=run_rest_polling, daemon=True).start()

    app.run(host='0.0.0.0', port=8080, use_reloader=False)

if __name__ == '__main__':
    main()
