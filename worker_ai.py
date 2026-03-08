"""
Cloudflare Workers AI Module for dopamine-hardware bridge.
Provides text generation, structured responses, and text-to-speech synthesis.
"""

import os
import json
import logging
import requests
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
    "for task management events. Keep it under 3 sentences. Be warm, positive, and actionable."
)


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
    """
    Sanitizes output file paths to prevent path traversal attacks.

    Args:
        output_path: The requested output path
        default_dir: Default directory for output files

    Returns:
        Sanitized absolute path within the default directory

    Raises:
        ValueError: If path traversal is detected
    """
    # Resolve to absolute path and normalize
    path = Path(output_path).resolve()

    # If path is relative or empty, place in default directory
    if not output_path or output_path.startswith('.'):
        path = Path(default_dir).resolve() / Path(output_path).name

    # Ensure path is within default directory or /tmp
    allowed_dirs = [Path(default_dir).resolve(), Path("/tmp").resolve()]

    # Check if path is within any allowed directory
    try:
        for allowed_dir in allowed_dirs:
            if path.is_relative_to(allowed_dir):
                return str(path)
    except (ValueError, AttributeError):
        # Fallback for Python < 3.9 (no is_relative_to)
        for allowed_dir in allowed_dirs:
            try:
                path.relative_to(allowed_dir)
                return str(path)
            except ValueError:
                continue

    # If not in allowed directory, create safe path in default directory
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
    """
    Generates text using Cloudflare AI Gateway.

    WARNING: This function passes prompts directly to an LLM. User-supplied input
    may contain prompt injection attempts. For untrusted input, consider validating
    or sanitizing the prompt, or using a more restrictive system prompt.

    Args:
        prompt: The user prompt/question
        model: The AI model to use (default: gpt-oss-120b)
        temperature: Response creativity (0.0-1.0)
        max_tokens: Maximum response length
        system_prompt: Optional system instruction

    Returns:
        Generated text string, or None on failure
    """
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
    """
    Generates a structured JSON response using Cloudflare AI Gateway.

    WARNING: This function passes prompts directly to an LLM. User-supplied input
    may contain prompt injection attempts. For untrusted input, consider validating
    or sanitizing the prompt.

    Args:
        prompt: The user prompt/question
        json_schema: Optional expected JSON schema description
        model: The AI model to use
        temperature: Response creativity (lower = more deterministic)
        max_tokens: Maximum response length
        system_prompt: Optional system instruction

    Returns:
        Parsed JSON dictionary, or None on failure
    """
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
            # Default system prompt for JSON responses
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
    """
    Generates text-to-speech audio using Cloudflare's Deepgram Aura-2 model.

    Args:
        text: Text to synthesize
        output_path: Where to save the audio file (will be sanitized to prevent path traversal)
        speaker: Voice to use (luna, hermes, vesta, thalia, etc.)

    Returns:
        Path to saved audio file, or None on failure
    """
    try:
        # Sanitize output path to prevent path traversal attacks
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

        # Stream response to handle large audio files efficiently
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


# --- Task Completion Audio Generator ---
def generate_task_completion_audio(
    task_name: str,
    action: str,
    minutes_spent: Optional[int] = None,
    other_tasks: Optional[List[str]] = None,
    recommended_next: Optional[str] = None,
    output_path: str = "task_completion.mp3",
    speaker: str = "luna"
) -> Optional[str]:
    """
    Generates motivational audio for task completion events.

    WARNING: This function uses AI to generate messages. User inputs (task_name, action)
    are passed directly to the LLM. For untrusted input, consider sanitizing task_name
    and validating action against a whitelist.

    Args:
        task_name: Name of the task
        action: Action taken (complete, paused, started, etc.)
        minutes_spent: Time spent on task (for paused/completed)
        other_tasks: List of remaining tasks
        recommended_next: AI recommendation for next task
        output_path: Where to save the audio file (will be sanitized to prevent path traversal)
        speaker: Voice to use

    Returns:
        Path to saved audio file, or None on failure
    """
    try:
        # Build context-aware message
        action_lower = action.lower()

        if action_lower in ["complete", "completed"]:
            prompt = f"Task '{task_name}' has been completed"
            if minutes_spent:
                prompt += f" after {minutes_spent} minutes"
            prompt += ". Provide a celebratory message"
            if other_tasks:
                prompt += f" and recommend starting one of these tasks: {', '.join(other_tasks[:3])}"
            if recommended_next:
                prompt += f". Especially recommend: {recommended_next}"

        elif action_lower in ["paused", "pause"]:
            prompt = f"Task '{task_name}' has been paused"
            if minutes_spent:
                prompt += f" after {minutes_spent} minutes of work"
            prompt += ". Provide an encouraging message with advice on staying focused when they return"

        elif action_lower in ["started", "start", "resumed", "resume"]:
            prompt = f"Task '{task_name}' has been {action_lower}. Provide a motivating message to help them focus"

        else:
            prompt = f"Task '{task_name}' status is now '{action}'. Provide a brief supportive message"

        logger.info(f"Generating motivational message for action: {action}")
        message = generate_text(
            prompt=prompt,
            system_prompt=_TASK_AUDIO_SYSTEM_PROMPT,
            temperature=0.8,
            max_tokens=256
        )

        if not message:
            # Fallback to simple message
            message = f"Task {task_name} has been {action_lower}"
            if minutes_spent:
                message += f" after {minutes_spent} minutes"
            logger.warning("Using fallback message due to AI generation failure")

        # Generate speech
        full_message = message
        logger.info(f"Final message: {full_message}")

        result = generate_voice(
            text=full_message,
            output_path=output_path,
            speaker=speaker
        )

        if result:
            # Return info about which sound effect to play first
            sound_file = _SOUND_MAP.get(action_lower, "started.wav")
            logger.info(f"Play sound effect '{sound_file}' before audio message")

        return result

    except Exception as e:
        logger.error(f"Task completion audio generation failed: {e}", exc_info=True)
        return None


# --- Hardware Diagnostics (Reusable from scan_usb_with_ai.py) ---
def diagnose_hardware(
    lsusb_output: str,
    udev_rules: str,
    app_code: str,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b"
) -> Optional[Dict[str, Any]]:
    """
    AI-powered hardware configuration diagnostics.
    Analyzes USB devices, udev rules, and application code for mismatches.

    WARNING: This function passes system configuration directly to an LLM.
    While this is typically trusted data, be aware of potential prompt injection
    if any of the input sources could be compromised.

    Args:
        lsusb_output: Output from lsusb command
        udev_rules: Contents of udev rules file
        app_code: Hardware configuration code
        model: AI model to use

    Returns:
        Diagnostic results with 'analysis', 'mismatch_found', and 'required_modifications'
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


# --- Module Testing ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("=== Cloudflare Workers AI Module Test ===\n")

    # Test 1: Text Generation
    print("1. Testing text generation...")
    text = generate_text("What is edge computing in one sentence?", max_tokens=100)
    if text:
        print(f"✓ Generated: {text}\n")
    else:
        print("✗ Text generation failed\n")

    # Test 2: Structured Response
    print("2. Testing structured response...")
    schema = {
        "summary": "string - one sentence summary",
        "key_points": "array of strings - 2-3 key points",
        "sentiment": "string - positive/neutral/negative"
    }
    structured = generate_structured_response(
        prompt="Analyze this: Edge computing enables low-latency processing at the network edge.",
        json_schema=schema
    )
    if structured:
        print(f"✓ Generated: {json.dumps(structured, indent=2)}\n")
    else:
        print("✗ Structured response failed\n")

    # Test 3: Text-to-Speech
    print("3. Testing text-to-speech...")
    audio_path = generate_voice(
        text="The dopamine hardware bridge is operational.",
        output_path="/tmp/test_tts.mp3",
        speaker="luna"
    )
    if audio_path:
        print(f"✓ Audio saved to: {audio_path}\n")
    else:
        print("✗ TTS generation failed\n")

    # Test 4: Task Completion Audio
    print("4. Testing task completion audio...")
    task_audio = generate_task_completion_audio(
        task_name="Write Documentation",
        action="completed",
        minutes_spent=45,
        other_tasks=["Review Code", "Deploy App"],
        output_path="/tmp/test_task.mp3"
    )
    if task_audio:
        print(f"✓ Task audio saved to: {task_audio}\n")
    else:
        print("✗ Task completion audio failed\n")

    print("=== Test Complete ===")
