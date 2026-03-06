import os

VENDOR_ID = 0x04b8
PRODUCT_ID = 0x0e28
WORKER_URL = "https://dopamine.hacolby.workers.dev"
WS_URL = "wss://dopamine.hacolby.workers.dev/api/printer/ws"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dopamine_logs.db')
