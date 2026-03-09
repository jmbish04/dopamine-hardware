"""
Configuration and utilities for Cloudflare AI integration.
"""
import os
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# --- Module-level Constants ---
SOUND_MAP = {
    "complete": "done.wav",
    "completed": "done.wav",
    "paused": "paused.wav",
    "pause": "paused.wav",
    "started": "started.wav",
    "start": "started.wav",
    "resumed": "started.wav",
    "resume": "started.wav"
}

TASK_AUDIO_SYSTEM_PROMPT = (
    "You are a supportive productivity coach. Generate brief, encouraging messages "
    "for task management events. Keep it under 2 sentences. Be warm, positive, and actionable for someone with ADHD."
)

MALE_VOICES = ["hermes", "perseus", "angus", "brian", "orpheus"]
FEMALE_VOICES = ["luna", "vesta", "thalia", "aura", "stella"]


def get_config() -> Dict[str, str]:
    """Loads Cloudflare AI credentials from environment variables."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ.get("CF_ACCOUNT_ID")
    api_token = (
        os.environ.get("CLOUDFLARE_AI_GATEWAY_TOKEN")
        or os.environ.get("CF_AI_GATEWAY_TOKEN")
        or os.environ.get("CLOUDFLARE_API_TOKEN")
        or os.environ.get("CF_API_TOKEN")
    )
    gateway_name = os.environ.get("CLOUDFLARE_GATEWAY_NAME") or os.environ.get("CF_GATEWAY_NAME", "default-gateway")

    if not account_id or not api_token:
        raise ValueError(
            "Missing Cloudflare credentials. Set CLOUDFLARE_ACCOUNT_ID and "
            "CLOUDFLARE_API_TOKEN (or CF_ACCOUNT_ID and CF_API_TOKEN) environment variables."
        )

    return {
        "account_id": account_id,
        "api_token": api_token,
        "gateway_name": gateway_name
    }


def sanitize_output_path(output_path: str, default_dir: str = "/tmp") -> str:
    """Sanitize output path to prevent directory traversal attacks."""
    path = Path(output_path).resolve()
    if not output_path or output_path.startswith('.'):
        path = Path(default_dir).resolve() / Path(output_path).name

    allowed_dirs = [Path(default_dir).resolve(), Path("/tmp").resolve()]
    try:
        for allowed_dir in allowed_dirs:
            if path.is_relative_to(allowed_dir):
                return str(path)
    except (ValueError, AttributeError):
        for allowed_dir in allowed_dirs:
            try:
                path.relative_to(allowed_dir)
                return str(path)
            except ValueError:
                continue

    safe_filename = Path(output_path).name
    if not safe_filename or safe_filename in ('.', '..'):
        safe_filename = "output.mp3"

    safe_path = Path(default_dir).resolve() / safe_filename
    logger.warning(f"Path traversal attempt blocked: {output_path} -> {safe_path}")
    return str(safe_path)
