"""
Thermal printer interface for Epson TM-T20III.
Provides thread-safe printing with job deduplication and ESC/POS formatting.
"""
import logging
import threading
import requests
import re
from datetime import datetime
from escpos.printer import Usb
from config import VENDOR_ID, PRODUCT_ID, WORKER_URL

# Printer state
printed_jobs = set()
printer_lock = threading.Lock()

def _play_announcement_audio_async(task_name):
    """
    Asynchronously generate and play announcement audio for new tasks.
    This runs in a separate thread to avoid blocking the printer.
    """
    try:
        # Import here to avoid circular dependency issues
        import ai
        from audio import play_audio_file

        # Generate announcement audio
        audio_path = ai.generate_announcement_audio(task_name)

        # Play the audio file
        if audio_path:
            play_audio_file(audio_path)

    except Exception as e:
        logging.error(f"Failed to generate/play announcement audio: {e}")

def get_printer():
    """Initialize USB printer connection."""
    try:
        return Usb(VENDOR_ID, PRODUCT_ID)
    except Exception as e:
        logging.error(f"USB Printer error: {repr(e)}")
        return None

def _sanitize_escpos_input(text):
    """Remove or escape potentially dangerous ESC/POS control sequences and strip emoji."""
    if not text:
        return ""

    # Remove emoji and other non-ASCII characters that printer can't handle
    # Keep only printable ASCII characters (32-126) plus newline (10) and tab (9)
    text = ''.join(char for char in text if ord(char) < 128 and (32 <= ord(char) <= 126 or ord(char) in (9, 10)))

    # Remove ESC/POS control sequences (ESC followed by any character)
    text = re.sub(r'\x1b.', '', text)

    # Limit length to prevent abuse
    return text[:512]

def _format_timestamp(timestamp):
    """Format a Unix timestamp or ISO string to readable date."""
    if not timestamp:
        return ""

    try:
        # Try parsing as Unix timestamp (seconds or milliseconds)
        if isinstance(timestamp, (int, float)):
            if timestamp > 10000000000:  # Milliseconds
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        # Try parsing as ISO string
        elif isinstance(timestamp, str):
            # Handle ISO format
            if 'T' in timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d %H:%M")
            return timestamp
    except Exception:
        return str(timestamp)

    return str(timestamp)

def print_and_ack(data):
    """
    Print a task receipt with all available data.

    Args:
        data: Dictionary containing task information. Expected fields:
            - id (required): Job ID for tracking
            - taskId: Task identifier
            - title: Task title
            - description: Task description
            - dueDate: Due date timestamp
            - status: Task status
            - createdAt: Creation timestamp
            - receiptQrValue: Short ID for barcode
            - Any other fields will be printed as key:value
    """
    job_id = data.get('id')
    if not job_id:
        logging.error("print_and_ack called without job ID")
        return False

    if job_id in printed_jobs:
        return True

    with printer_lock:
        if job_id in printed_jobs:
            return True
        p = get_printer()
        if not p:
            return False
        try:
            p.hw("INIT")

            # Header
            p.set(align='center', font='a', width=2, height=2, bold=True)
            p.text("DOPAMINE\n")
            p.set(align='center', font='a', width=1, height=1, bold=False)
            p.text("-" * 32 + "\n\n")

            # Well-known fields in specific order
            p.set(align='left', font='a', bold=False)

            # Track which fields we've already printed
            printed_fields = set()

            # Print taskId if available
            task_id = data.get('taskId') or data.get('receiptQrValue') or job_id
            task_id_clean = _sanitize_escpos_input(str(task_id))
            p.set(bold=True)
            p.text(f"Task ID: {task_id_clean}\n")
            p.set(bold=False)
            printed_fields.update(['taskId', 'receiptQrValue', 'id'])

            # Print title
            if data.get('title'):
                title_clean = _sanitize_escpos_input(str(data['title']))
                p.text(f"Title: {title_clean}\n")
                printed_fields.add('title')

            # Print description (allow multiline)
            if data.get('description'):
                desc_clean = _sanitize_escpos_input(str(data['description']))
                p.text(f"Description: {desc_clean}\n")
                printed_fields.add('description')

            # Print status
            if data.get('status'):
                status_clean = _sanitize_escpos_input(str(data['status']))
                p.text(f"Status: {status_clean}\n")
                printed_fields.add('status')

            # Print due date
            if data.get('dueDate'):
                due_date_formatted = _format_timestamp(data['dueDate'])
                due_date_clean = _sanitize_escpos_input(due_date_formatted)
                p.text(f"Due: {due_date_clean}\n")
                printed_fields.add('dueDate')

            # Print created at
            if data.get('createdAt'):
                created_formatted = _format_timestamp(data['createdAt'])
                created_clean = _sanitize_escpos_input(created_formatted)
                p.text(f"Created: {created_clean}\n")
                printed_fields.add('createdAt')

            # Print any remaining fields
            remaining_fields = {k: v for k, v in data.items() if k not in printed_fields and v is not None}
            if remaining_fields:
                p.text("\n")
                for key, value in sorted(remaining_fields.items()):
                    # Format key nicely (camelCase to Title Case)
                    key_formatted = re.sub(r'([A-Z])', r' \1', key).title().strip()
                    value_str = str(value)
                    # Handle timestamps
                    if 'date' in key.lower() or 'time' in key.lower() or key.lower().endswith('at'):
                        value_str = _format_timestamp(value)
                    value_clean = _sanitize_escpos_input(value_str)[:100]  # Limit value length
                    p.text(f"{key_formatted}: {value_clean}\n")

            # Barcode
            p.text("\n")
            p.set(align='center')
            # 1D Barcode Logic: {{B forces Character Subset B to allow alphanumeric text
            safe_barcode = ''.join(c for c in task_id_clean if c.isalnum() or c in '-_')[:48]
            if safe_barcode:
                p.barcode(f"{{B{safe_barcode}", "CODE128", height=80, width=3, pos="BELOW")
            p.text("\n\n\n")

            p.cut()
            p.close()

            printed_jobs.add(job_id)
            logging.info(f"✅ Printed task: {task_id_clean}")
            requests.post(f"{WORKER_URL}/api/printer/ack", json={"job_id": job_id}, timeout=5)

            # Trigger announcement audio asynchronously for new print jobs
            task_name = data.get('title') or task_id_clean
            audio_thread = threading.Thread(
                target=_play_announcement_audio_async,
                args=(task_name,),
                daemon=True
            )
            audio_thread.start()

            return True
        except Exception as e:
            logging.error(f"Print hardware failed: {e}")
            if p:
                p.close()
            return False
