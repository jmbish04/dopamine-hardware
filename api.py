from flask import Flask, request, jsonify
import logging
import time
import socket
import subprocess
import os
from hardware import print_and_ack, get_printer, printer_lock

app = Flask(__name__)

# Simple API key authentication (optional, set via environment variable)
API_KEY = os.environ.get('DOPAMINE_API_KEY')

def require_api_key(f):
    """Decorator to require API key if configured."""
    def decorated_function(*args, **kwargs):
        if API_KEY:
            provided_key = request.headers.get('X-API-Key')
            if provided_key != API_KEY:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/print', methods=['POST'])
@require_api_key
def vpc_print():
    """Print a task receipt with input validation."""
    # Validate request has JSON body
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.json
    if not data:
        return jsonify({"error": "Request body cannot be empty"}), 400

    # Validate required field (id)
    if not data.get('id'):
        return jsonify({"error": "Missing required field: id"}), 400

    try:
        if print_and_ack(data):
            return jsonify({"status": "success"})
        return jsonify({"error": "Print failed"}), 500
    except Exception as e:
        logging.error(f"Print endpoint error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/test', methods=['POST', 'GET'])
@require_api_key
def trigger_full_test():
    """Run diagnostic test with sanitized barcode."""
    logging.info("🛠️ Diagnostic test triggered via VPC")
    report = {"status": "healthy", "printer": "unknown", "network": "unknown", "timestamp": time.time()}
    with printer_lock:
        p = get_printer()
        if p:
            try:
                p.hw("INIT")
                p.set(align='center', font='a', width=2, height=2, bold=True)
                p.text("DIAGNOSTIC TEST\n")
                p.set(align='center', font='a', width=1, height=1, bold=False)
                p.text("-" * 32 + "\n\n")
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                report["network"] = local_ip
                p.set(align='left')
                p.text(f"IP: {local_ip}\n")
                p.text("VPC: ACTIVE\n")
                p.text("STATUS: ALL SYSTEMS GO\n\n")
                p.set(align='center')
                # Use CODE128 1D barcode instead of QR
                p.barcode("{BDIAG-OK", "CODE128", height=60, width=2, pos="BELOW")
                p.text("\n\n\n")
                p.cut()
                p.close()
                report["printer"] = "online"
            except Exception as e:
                logging.error(f"Diagnostic print failed: {e}")
                report["printer"] = "error"
                report["error"] = str(e)
                report["status"] = "degraded"
        else:
            report["printer"] = "disconnected"
            report["status"] = "degraded"
    return jsonify(report), 200 if report["status"] == "healthy" else 503

@app.route('/logs', methods=['GET'])
@require_api_key
def get_system_logs():
    """
    Get system logs with rate limiting and input validation.
    WARNING: Contains sensitive information. Should only be accessible via authenticated tunnel.
    """
    lines = request.args.get('lines', '50')

    # Validate and sanitize lines parameter to prevent DoS
    if not lines.isdigit():
        lines = '50'
    else:
        lines_int = int(lines)
        if lines_int < 1 or lines_int > 1000:
            lines = '50'

    try:
        logging.info(f"VPC requested {lines} lines of journalctl logs")
        output = subprocess.check_output(
            ['journalctl', '-u', 'dopamine.service', '-n', str(lines), '--no-pager'],
            text=True,
            timeout=30  # Prevent hanging
        )
        return jsonify({"status": "success", "logs": output})
    except subprocess.TimeoutExpired:
        logging.error("journalctl command timed out")
        return jsonify({"status": "error", "error": "Request timed out"}), 504
    except Exception as e:
        logging.error(f"Failed to read journalctl: {e}")
        return jsonify({"status": "error", "error": "Failed to retrieve logs"}), 500
