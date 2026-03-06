"""
app.py – Dopamine Hardware Bridge
Flask-based HTTP bridge that exposes REST endpoints for printing receipts
and generating QR codes via an ESC/POS USB receipt printer.
"""

import io
import logging

import qrcode
from escpos.printer import Usb
from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default USB vendor/product IDs for a common ESC/POS printer.
# Override via the PRINTER_VENDOR_ID / PRINTER_PRODUCT_ID environment
# variables or pass them in the JSON body of each request.
DEFAULT_VENDOR_ID = 0x04B8   # Epson
DEFAULT_PRODUCT_ID = 0x0202


def get_printer(vendor_id=DEFAULT_VENDOR_ID, product_id=DEFAULT_PRODUCT_ID):
    """Return an open Usb printer instance."""
    return Usb(vendor_id, product_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    return jsonify({"status": "ok"})


@app.route("/print", methods=["POST"])
def print_text():
    """
    Print plain text to the receipt printer.

    Expected JSON body:
        {
            "text": "Hello, world!",
            "cut":  true          // optional, default true
        }
    """
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "")
    cut = data.get("cut", True)

    if not text:
        return jsonify({"error": "text field is required"}), 400

    try:
        printer = get_printer(
            vendor_id=data.get("vendor_id", DEFAULT_VENDOR_ID),
            product_id=data.get("product_id", DEFAULT_PRODUCT_ID),
        )
        printer.text(text + "\n")
        if cut:
            printer.cut()
        printer.close()
        logger.info("Printed %d chars", len(text))
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("Print failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/qr", methods=["POST"])
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

        printer = get_printer(
            vendor_id=data.get("vendor_id", DEFAULT_VENDOR_ID),
            product_id=data.get("product_id", DEFAULT_PRODUCT_ID),
        )
        printer.image(buf)
        if cut:
            printer.cut()
        printer.close()
        logger.info("Printed QR for: %s", qr_data)
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("QR print failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/receipt", methods=["POST"])
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
        printer = get_printer(
            vendor_id=data.get("vendor_id", DEFAULT_VENDOR_ID),
            product_id=data.get("product_id", DEFAULT_PRODUCT_ID),
        )

        printer.set(align="center", bold=True, width=2, height=2)
        printer.text(title + "\n")
        printer.set(align="left", bold=False, width=1, height=1)
        printer.text("-" * 32 + "\n")

        for item in items:
            name = str(item.get("name", ""))
            try:
                price = float(item.get("price", 0))
            except (TypeError, ValueError):
                return jsonify({"error": f"invalid price for item '{name}'"}), 400
            line = f"{name:<24}{price:>8.2f}\n"
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
            printer.set(align="center")
            printer.text("\n" + footer + "\n")

        if cut:
            printer.cut()

        printer.close()
        logger.info("Printed receipt: %s", title)
        return jsonify({"status": "printed"})
    except Exception as exc:
        logger.exception("Receipt print failed")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
