import os

VENDOR_ID = 0x04b8
PRODUCT_ID = 0x0e28
WORKER_URL = "https://dopamine.hacolby.workers.dev"
WS_URL = "wss://dopamine.hacolby.workers.dev/api/printer/ws"
# Store database in project root, not inside src/ directory, to prevent data loss during deployments
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'dopamine_logs.db'))
