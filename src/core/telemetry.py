import sqlite3
import logging
import requests
from src.core.core_logger import log_queue
from src.core.config import DB_PATH, WORKER_URL

def telemetry_worker():
    conn = sqlite3.connect(DB_PATH)
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
                "level": log_entry['level'],
                "message": log_entry['message'],
                "network": "vpc-tunnel"
            }
            requests.post(f"{WORKER_URL}/api/printer/telemetry", json=cf_payload, timeout=3)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to send telemetry to cloud: {e}")
