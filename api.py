from flask import Flask, request, jsonify
import logging
import time
import socket
import subprocess
from hardware import print_and_ack, get_printer, printer_lock

app = Flask(__name__)

@app.route('/print', methods=['POST'])
def vpc_print():
    data = request.json
    if print_and_ack(data['id'], data['title']):
        return jsonify({"status": "success"})
    return jsonify({"error": "Print failed"}), 500

@app.route('/test', methods=['POST', 'GET'])
def trigger_full_test():
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
                p.qr("DIAGNOSTIC-OK", size=6, native=True)
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
def get_system_logs():
    lines = request.args.get('lines', '50')
    try:
        logging.info("VPC requested journalctl logs")
        output = subprocess.check_output(['journalctl', '-u', 'dopamine.service', '-n', str(lines), '--no-pager'], text=True)
        return jsonify({"status": "success", "logs": output})
    except Exception as e:
        logging.error(f"Failed to read journalctl: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500
