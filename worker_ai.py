# worker_ai.py
"""
Cloudflare Workers AI Module for dopamine-hardware bridge.
Provides text generation, structured responses, and text-to-speech synthesis.
"""

import os
import json
import logging
import requests
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from openai import OpenAI

logger = logging.getLogger(__name__)

# --- Module-level Constants ---
_SOUND_MAP = {
    "complete": "done.wav",
    "completed": "done.wav",
    "paused": "paused.wav",
    "pause": "paused.wav",
    "started": "started.wav",
    "start": "started.wav",
    "resumed": "started.wav",
    "resume": "started.wav"
}

_TASK_AUDIO_SYSTEM_PROMPT = (
    "You are a supportive productivity coach. Generate brief, encouraging messages "
    "for task management events. Keep it under 2 sentences. Be warm, positive, and actionable for someone with ADHD."
)

_MALE_VOICES = ["hermes", "perseus", "angus", "brian", "orpheus"]
_FEMALE_VOICES = ["luna", "vesta", "thalia", "aura", "stella"]


# --- Configuration ---
def _get_config() -> Dict[str, str]:
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


def _sanitize_output_path(output_path: str, default_dir: str = "/tmp") -> str:
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


# --- Text Generation ---
def generate_text(
    prompt: str,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None
) -> Optional[str]:
    try:
        config = _get_config()
        base_url = f"https://gateway.ai.cloudflare.com/v1/{config['account_id']}/{config['gateway_name']}/compat"

        client = OpenAI(
            base_url=base_url,
            api_key=config['api_token'],
            default_headers={"cf-aig-authorization": f"Bearer {config['api_token']}"}
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"Generating text with model {model} (temp={temperature}, max_tokens={max_tokens})")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        result = response.choices[0].message.content
        logger.info(f"Generated {len(result)} characters")
        return result

    except Exception as e:
        logger.error(f"Text generation failed: {e}", exc_info=True)
        return None


# --- Structured Response Generation ---
def generate_structured_response(
    prompt: str,
    json_schema: Optional[Dict[str, Any]] = None,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    try:
        config = _get_config()
        base_url = f"https://gateway.ai.cloudflare.com/v1/{config['account_id']}/{config['gateway_name']}/compat"

        client = OpenAI(
            base_url=base_url,
            api_key=config['api_token'],
            default_headers={"cf-aig-authorization": f"Bearer {config['api_token']}"}
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            schema_desc = f" The response must conform to this schema: {json.dumps(json_schema)}" if json_schema else ""
            messages.append({
                "role": "system",
                "content": f"You must respond with valid JSON only, no additional text.{schema_desc}"
            })

        messages.append({"role": "user", "content": prompt})

        logger.info(f"Generating structured response with model {model}")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("AI returned empty content")
            return None

        result = json.loads(content)
        logger.info(f"Parsed structured response with {len(result)} keys")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Structured response generation failed: {e}", exc_info=True)
        return None


# --- Text-to-Speech (TTS) ---
def generate_voice(
    text: str,
    output_path: str = "output.mp3",
    speaker: str = "luna"
) -> Optional[str]:
    try:
        safe_output_path = _sanitize_output_path(output_path)
        config = _get_config()
        account_id = config['account_id']
        api_token = config['api_token']

        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/deepgram/aura-2-en"

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "text": text,
            "speaker": speaker
        }

        logger.info(f"Generating speech: '{text[:50]}...' with voice '{speaker}'")
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)

        if response.status_code == 200:
            with open(safe_output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Audio saved to {safe_output_path}")
            return safe_output_path
        else:
            logger.error(f"TTS failed. Status: {response.status_code}, Details: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Voice generation failed: {e}", exc_info=True)
        return None


# --- Multi-Speaker Audio Generators ---
def generate_multi_speaker_task_audio(
    task_name: str,
    action: str,
    output_prefix: str = "/tmp/task_multi"
) -> List[str]:
    """
    Generates two audio files: one confirmation (male), one motivation (female).
    """
    try:
        paths = []
        action_lower = action.lower()
        
        # 1. Speaker 1 (Confirmation - Male Voice)
        male_voice = random.choice(_MALE_VOICES)
        confirmation_text = f"Task '{task_name}' has been {action_lower}."
        path1 = generate_voice(confirmation_text, f"{output_prefix}_1.mp3", speaker=male_voice)
        if path1:
            paths.append(path1)

        # 2. Speaker 2 (Motivation - Female Voice)
        female_voice = random.choice(_FEMALE_VOICES)
        prompt = f"The user just marked '{task_name}' as {action_lower}. Provide a very brief, encouraging 1 to 2 sentence response."
        motivation_text = generate_text(prompt, system_prompt=_TASK_AUDIO_SYSTEM_PROMPT, temperature=0.8, max_tokens=150)
        
        if motivation_text:
            path2 = generate_voice(motivation_text, f"{output_prefix}_2.mp3", speaker=female_voice)
            if path2:
                paths.append(path2)
                
        return paths
    except Exception as e:
        logger.error(f"Multi-speaker audio generation failed: {e}", exc_info=True)
        return []

def generate_announcement_audio(
    task_name: str, 
    output_path: str = "/tmp/announcement.mp3"
) -> Optional[str]:
    """Generates an announcement for a new print job using a default AI voice."""
    try:
        text = f"New task received: {task_name}"
        return generate_voice(text, output_path, speaker="aura")
    except Exception as e:
        logger.error(f"Announcement generation failed: {e}", exc_info=True)
        return None

# --- Legacy Single Task Completion ---
def generate_task_completion_audio(
    task_name: str,
    action: str,
    minutes_spent: Optional[int] = None,
    other_tasks: Optional[List[str]] = None,
    recommended_next: Optional[str] = None,
    output_path: str = "task_completion.mp3",
    speaker: str = "luna"
) -> Optional[str]:
    try:
        action_lower = action.lower()

        if action_lower in ["complete", "completed"]:
            prompt = f"Task '{task_name}' has been completed"
            if minutes_spent: prompt += f" after {minutes_spent} minutes"
            prompt += ". Provide a celebratory message"
            if other_tasks: prompt += f" and recommend starting one of these tasks: {', '.join(other_tasks[:3])}"
            if recommended_next: prompt += f". Especially recommend: {recommended_next}"
        elif action_lower in ["paused", "pause"]:
            prompt = f"Task '{task_name}' has been paused"
            if minutes_spent: prompt += f" after {minutes_spent} minutes of work"
            prompt += ". Provide an encouraging message with advice on staying focused when they return"
        elif action_lower in ["started", "start", "resumed", "resume"]:
            prompt = f"Task '{task_name}' has been {action_lower}. Provide a motivating message to help them focus"
        else:
            prompt = f"Task '{task_name}' status is now '{action}'. Provide a brief supportive message"

        logger.info(f"Generating motivational message for action: {action}")
        message = generate_text(prompt=prompt, system_prompt=_TASK_AUDIO_SYSTEM_PROMPT, temperature=0.8, max_tokens=256)

        if not message:
            message = f"Task {task_name} has been {action_lower}"
            if minutes_spent: message += f" after {minutes_spent} minutes"

        full_message = message
        logger.info(f"Final message: {full_message}")

        result = generate_voice(text=full_message, output_path=output_path, speaker=speaker)
        if result:
            sound_file = _SOUND_MAP.get(action_lower, "started.wav")
            logger.info(f"Play sound effect '{sound_file}' before audio message")
        return result

    except Exception as e:
        logger.error(f"Task completion audio generation failed: {e}", exc_info=True)
        return None


# --- Hardware Diagnostics ---
def diagnose_hardware(
    lsusb_output: str,
    udev_rules: str,
    app_code: str,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b"
) -> Optional[Dict[str, Any]]:
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
