"""
app.py – Dopamine Hardware Bridge
Flask-based HTTP bridge that exposes REST endpoints for printing receipts
and generating QR codes via an ESC/POS USB receipt printer.
"""

import io
import logging
import os
import re
from contextlib import contextmanager
from functools import wraps

import qrcode
from escpos.printer import Usb
from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
API_KEY = os.environ.get("DOPAMINE_API_KEY")
BIND_HOST = os.environ.get("DOPAMINE_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("DOPAMINE_BIND_PORT", "5000"))

# Allowlist of supported printer devices (vendor_id, product_id)
# Add your specific printer models here
ALLOWED_PRINTERS = [
    (0x04B8, 0x0202),  # Epson TM-T88V
    (0x04B8, 0x0E03),  # Epson TM-T20
    (0x0519, 0x0003),  # Star Micronics
]

# Use the first printer in the allowlist as default
DEFAULT_VENDOR_ID, DEFAULT_PRODUCT_ID = ALLOWED_PRINTERS[0]


def sanitize_text(text):
    """
    Sanitize text input to prevent ESC/POS command injection.
    Removes control characters except newline, tab, and carriage return.
    """
    # Allow printable ASCII, newline, tab, carriage return
    # Remove ESC (0x1B) and other control characters that could be exploited
    sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    return sanitized


def require_api_key(f):
    """Decorator to require API key authentication if configured."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if API_KEY:
            provided_key = request.headers.get("X-API-Key")
            import hmac
            if not provided_key or not hmac.compare_digest(provided_key, API_KEY):
                logger.warning("Unauthorized access attempt from %s", request.remote_addr)
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


@contextmanager
def get_printer(vendor_id=DEFAULT_VENDOR_ID, product_id=DEFAULT_PRODUCT_ID):
    """
    Context manager that returns an open Usb printer instance.
    Ensures printer connection is always properly closed.
    """
    # Validate against allowlist
    if (vendor_id, product_id) not in ALLOWED_PRINTERS:
        raise ValueError(f"Printer {vendor_id:04x}:{product_id:04x} not in allowlist")

    printer = None
    try:
        printer = Usb(vendor_id, product_id)
        yield printer
    finally:
        if printer:
            try:
                printer.close()
            except Exception as e:
                logger.error("Error closing printer: %s", e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    return jsonify({"status": "ok"})


@app.route("/print", methods=["POST"])
@require_api_key
def print_text():
    """
    Print plain text to the receipt printer.

    Expected JSON body:
        {
            "text": "Hello, world!",
            "cut":  true          // optional, default true
        }
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    cut = data.get("cut", True)

    if not text:
        return jsonify({"error": "text field is required"}), 400

    try:
        # Sanitize input to prevent ESC/POS injection
        sanitized_text = sanitize_text(text)

        with get_printer() as printer:
            printer.text(sanitized_text + "\n")
            if cut:
                printer.cut()

        logger.info("Printed %d chars", len(sanitized_text))
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("Print failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/qr", methods=["POST"])
@require_api_key
def print_qr():
    """
    Print a QR code to the receipt printer.

    Expected JSON body:
        {
            "data":  "https://example.com",
            "size":  10,   // optional QR module size (pixels), default 10
            "cut":   true  // optional, default true
        }
    """
    data = request.get_json(force=True, silent=True) or {}
    qr_data = data.get("data", "")
    size = data.get("size", 10)
    cut = data.get("cut", True)

    if not qr_data:
        return jsonify({"error": "data field is required"}), 400

    try:
        size = int(size)
    except (TypeError, ValueError):
        return jsonify({"error": "size must be an integer"}), 400

    try:
        qr = qrcode.QRCode(box_size=size, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        with get_printer() as printer:
            printer.image(buf)
            if cut:
                printer.cut()

        logger.info("Printed QR for: %s", qr_data)
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("QR print failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/receipt", methods=["POST"])
@require_api_key
def print_receipt():
    """
    Print a structured receipt.

    Expected JSON body:
        {
            "title":   "My Shop",
            "items":   [{"name": "Widget", "price": 1.99}, ...],
            "total":   9.99,
            "footer":  "Thank you!",   // optional
            "cut":     true            // optional, default true
        }
    """
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title", "")
    items = data.get("items", [])
    total = data.get("total")
    footer = data.get("footer", "")
    cut = data.get("cut", True)

    if not title or not items or total is None:
        return jsonify({"error": "title, items, and total are required"}), 400

    try:
        with get_printer() as printer:
            # Sanitize title
            sanitized_title = sanitize_text(title)

            printer.set(align="center", bold=True, width=2, height=2)
            printer.text(sanitized_title + "\n")
            printer.set(align="left", bold=False, width=1, height=1)
            printer.text("-" * 32 + "\n")

            for item in items:
                name = str(item.get("name", ""))
                # Sanitize item name
                sanitized_name = sanitize_text(name)
                try:
                    price = float(item.get("price", 0))
                except (TypeError, ValueError):
                    return jsonify({"error": f"invalid price for item '{name}'"}), 400
                line = f"{sanitized_name:<24}{price:>8.2f}\n"
                printer.text(line)

            printer.text("-" * 32 + "\n")
            printer.set(bold=True)
            try:
                total_value = float(total)
            except (TypeError, ValueError):
                return jsonify({"error": "total must be a number"}), 400
            printer.text(f"{'TOTAL':<24}{total_value:>8.2f}\n")
            printer.set(bold=False)

            if footer:
                # Sanitize footer
                sanitized_footer = sanitize_text(footer)
                printer.set(align="center")
                printer.text("\n" + sanitized_footer + "\n")

            if cut:
                printer.cut()

        logger.info("Printed receipt: %s", title)
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("Receipt print failed")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host=BIND_HOST, port=BIND_PORT)
