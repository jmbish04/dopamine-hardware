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

# Validated Deepgram Aura 2 EN voices categorized by use-case
STATUS_VOICES = ["athena", "helena"]
MOTIVATION_VOICES = ["thalia", "helena"]


def _parse_comma_separated_list(value: str) -> list:
    """Parse a comma-separated string into a list."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def get_config() -> Dict[str, str]:
    """Loads Cloudflare AI credentials and TTS provider settings from environment variables."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ.get("CF_ACCOUNT_ID")
    api_token = (
        os.environ.get("CLOUDFLARE_AI_GATEWAY_TOKEN")
        or os.environ.get("CF_AI_GATEWAY_TOKEN")
        or os.environ.get("CLOUDFLARE_API_TOKEN")
        or os.environ.get("CF_API_TOKEN")
    )
    gateway_name = os.environ.get("CLOUDFLARE_GATEWAY_NAME") or os.environ.get("CF_GATEWAY_NAME", "default-gateway")

    # TTS Provider configuration
    tts_provider = os.environ.get("TTS_PROVIDER", "cloudflare").lower()
    deepgram_api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    deepgram_project_id = os.environ.get("DEEPGRAM_PROJECT_ID", "")

    # Voice and speed configuration with environment overrides
    status_voices_env = os.environ.get("TTS_STATUS_VOICES", "")
    status_voices = _parse_comma_separated_list(status_voices_env) if status_voices_env else STATUS_VOICES

    motivation_voices_env = os.environ.get("TTS_MOTIVATION_VOICES", "")
    motivation_voices = _parse_comma_separated_list(motivation_voices_env) if motivation_voices_env else MOTIVATION_VOICES

    try:
        status_speed = float(os.environ.get("TTS_STATUS_SPEED", "1.3"))
    except ValueError:
        logger.warning("Invalid TTS_STATUS_SPEED value, using default 1.3")
        status_speed = 1.3

    try:
        motivation_speed = float(os.environ.get("TTS_MOTIVATION_SPEED", "1.2"))
    except ValueError:
        logger.warning("Invalid TTS_MOTIVATION_SPEED value, using default 1.2")
        motivation_speed = 1.2

    # Validate credentials based on provider
    if tts_provider == "cloudflare":
        if not account_id or not api_token:
            raise ValueError(
                "Missing Cloudflare credentials. Set CLOUDFLARE_ACCOUNT_ID and "
                "CLOUDFLARE_API_TOKEN (or CF_ACCOUNT_ID and CF_API_TOKEN) environment variables."
            )
    elif tts_provider == "deepgram":
        if not deepgram_api_key:
            raise ValueError(
                "Missing Deepgram credentials. Set DEEPGRAM_API_KEY environment variable."
            )

    return {
        "account_id": account_id,
        "api_token": api_token,
        "gateway_name": gateway_name,
        "tts_provider": tts_provider,
        "deepgram_api_key": deepgram_api_key,
        "deepgram_project_id": deepgram_project_id,
        "status_voices": status_voices,
        "motivation_voices": motivation_voices,
        "status_speed": status_speed,
        "motivation_speed": motivation_speed
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
