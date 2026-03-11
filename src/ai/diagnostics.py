"""
Hardware diagnostics using AI for configuration analysis.
"""
import logging
from typing import Optional, Dict, Any
from .text import generate_structured_response

logger = logging.getLogger(__name__)


def diagnose_hardware(
    lsusb_output: str,
    udev_rules: str,
    app_code: str,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b"
) -> Optional[Dict[str, Any]]:
    """
    Analyze hardware configuration using AI to identify mismatches.

    Args:
        lsusb_output: Output from lsusb command showing connected USB devices
        udev_rules: Contents of udev rules file
        app_code: Application code containing hardware configuration
        model: AI model identifier

    Returns:
        Dict with keys: 'analysis', 'mismatch_found', 'required_modifications'
        or None on failure
    """
    system_prompt = (
        "You are a Codex Senior Engineer diagnosing a hardware bridge. Analyze the provided `lsusb` output "
        "against the user's `udev` rules and Python application code. "
        "Identify if the Vendor ID (VID) and Product ID (PID) for the connected thermal printer and barcode scanner "
        "match the hardcoded values in the files. "
        "You MUST return your response as a valid JSON object strictly containing three keys: "
        "'analysis' (string explaining the state), 'mismatch_found' (boolean true/false), and 'required_modifications' "
        "(string containing markdown diffs, or empty if no mismatch)."
    )

    prompt = (
        f"<lsusb_output>\n{lsusb_output}\n</lsusb_output>\n\n"
        f"<udev_rules>\n{udev_rules}\n</udev_rules>\n\n"
        f"<app_code>\n{app_code}\n</app_code>"
    )

    return generate_structured_response(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=0.2,
        max_tokens=4096
    )
