import logging
import time
from queue import Queue

log_queue = Queue()

class DualLoggerHandler(logging.Handler):
    def emit(self, record):
        log_queue.put({
            "timestamp": time.time(),
            "level": record.levelname,
            "message": self.format(record)
        })

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    dual_handler = DualLoggerHandler()
    dual_handler.setFormatter(formatter)
    logger.addHandler(dual_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configure websocket logger to show errors with full details
    logging.getLogger("websocket").setLevel(logging.ERROR)
