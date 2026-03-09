"""
Text-to-Speech (TTS) and audio generation using Cloudflare AI.
"""
import logging
import random
import requests
from typing import Optional, List
from .config import get_config, sanitize_output_path, TASK_AUDIO_SYSTEM_PROMPT, STATUS_VOICES, MOTIVATION_VOICES, SOUND_MAP
from .text import generate_text

logger = logging.getLogger(__name__)


def generate_voice(
    text: str,
    output_path: str = "output.mp3",
    speaker: str = "luna",
    speed: float = 1.0
) -> Optional[str]:
    """
    Generate speech audio from text using configured TTS provider (Deepgram or Cloudflare).

    Args:
        text: Text to convert to speech
        output_path: Where to save the audio file
        speaker: Voice identifier (e.g., "luna", "hermes", "athena")
        speed: Playback speed multiplier (e.g., 1.2, 1.3)

    Returns:
        Path to saved audio file or None on failure
    """
    try:
        safe_output_path = sanitize_output_path(output_path)
        config = get_config()
        tts_provider = config.get('tts_provider', 'cloudflare')

        logger.info(f"Generating speech with provider '{tts_provider}': '{text[:50]}...' voice='{speaker}' speed={speed}x")

        if tts_provider == "deepgram":
            # Use Deepgram native REST API
            deepgram_api_key = config['deepgram_api_key']
            url = f"https://api.deepgram.com/v1/speak?model=aura-2-{speaker}-en&speed={speed}"

            headers = {
                "Authorization": f"Token {deepgram_api_key}",
                "Content-Type": "application/json"
            }

            payload = {"text": text}

            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)

            if response.status_code == 200:
                with open(safe_output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"Audio saved to {safe_output_path}")
                return safe_output_path
            else:
                logger.error(f"Deepgram TTS failed. Status: {response.status_code}, Details: {response.text}")
                return None

        else:
            # Use Cloudflare Workers AI
            account_id = config['account_id']
            api_token = config['api_token']
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/deepgram/aura-2-en"

            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }

            # Including speed parameter; may be ignored or rejected by strict CF Gateway validation
            payload = {
                "text": text,
                "speaker": speaker,
                "speed": speed
            }

            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)

            if response.status_code == 200:
                with open(safe_output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"Audio saved to {safe_output_path}")
                return safe_output_path
            else:
                logger.error(f"Cloudflare TTS failed. Status: {response.status_code}, Details: {response.text}")
                return None

    except Exception as e:
        logger.error(f"Voice generation failed: {e}", exc_info=True)
        return None


def generate_multi_speaker_task_audio(
    task_name: str,
    action: str,
    output_prefix: str = "/tmp/task_multi"
) -> List[str]:
    """
    Generates two audio files: one confirmation, one motivation.

    Args:
        task_name: Name of the task
        action: Action taken (e.g., "completed", "started")
        output_prefix: Prefix for output files

    Returns:
        List of generated audio file paths
    """
    try:
        config = get_config()
        paths = []
        action_lower = action.lower()

        # 1. Speaker 1 (Confirmation / Status of task)
        status_voice = random.choice(config['status_voices'])
        confirmation_text = f"Task '{task_name}' has been {action_lower}."
        path1 = generate_voice(confirmation_text, f"{output_prefix}_1.mp3", speaker=status_voice, speed=config['status_speed'])
        if path1:
            paths.append(path1)

        # 2. Speaker 2 (Motivation)
        motivation_voice = random.choice(config['motivation_voices'])
        prompt = f"The user just marked '{task_name}' as {action_lower}. Provide a very brief, encouraging 1 to 2 sentence response."
        motivation_text = generate_text(prompt, system_prompt=TASK_AUDIO_SYSTEM_PROMPT, temperature=0.8, max_tokens=150)

        if motivation_text:
            path2 = generate_voice(motivation_text, f"{output_prefix}_2.mp3", speaker=motivation_voice, speed=config['motivation_speed'])
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
    """
    Generates an announcement for a new print job using a default AI voice.

    Args:
        task_name: Name of the task to announce
        output_path: Where to save the audio file

    Returns:
        Path to saved audio file or None on failure
    """
    try:
        text = f"New task received: {task_name}"
        return generate_voice(text, output_path, speaker="athena", speed=1.3)
    except Exception as e:
        logger.error(f"Announcement generation failed: {e}", exc_info=True)
        return None


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
    Generate a complete task audio message with sound effect mapping.

    Args:
        task_name: Name of the task
        action: Action taken (e.g., "complete", "paused", "started")
        minutes_spent: Optional minutes spent on task
        other_tasks: Optional list of other tasks to recommend
        recommended_next: Optional specific next task recommendation
        output_path: Where to save the audio file
        speaker: Voice identifier

    Returns:
        Path to saved audio file or None on failure
    """
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
        message = generate_text(prompt=prompt, system_prompt=TASK_AUDIO_SYSTEM_PROMPT, temperature=0.8, max_tokens=256)

        if not message:
            message = f"Task {task_name} has been {action_lower}"
            if minutes_spent: message += f" after {minutes_spent} minutes"

        full_message = message
        logger.info(f"Final message: {full_message}")

        # Applying the 1.2x motivational speed for standard completion legacy logic
        result = generate_voice(text=full_message, output_path=output_path, speaker=speaker, speed=1.2)
        if result:
            sound_file = SOUND_MAP.get(action_lower, "started.wav")
            logger.info(f"Play sound effect '{sound_file}' before audio message")
        return result

    except Exception as e:
        logger.error(f"Task completion audio generation failed: {e}", exc_info=True)
        return None
