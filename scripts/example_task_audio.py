#!/usr/bin/env python3
"""
Example: Integrating worker_ai with hardware.py for task completion events.

This demonstrates how to:
1. Generate AI-powered motivational messages for task events
2. Play audio feedback (sound effects + TTS) using the hardware
3. Integrate with the existing print_and_ack workflow
"""

import os
import sys
import subprocess
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker_ai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def play_audio_file(audio_path):
    """
    Plays an audio file using aplay (available on Raspberry Pi).
    Falls back gracefully if audio hardware is not available.
    """
    try:
        subprocess.run(
            ["aplay", "-q", audio_path],
            check=True,
            capture_output=True,
            timeout=30
        )
        logger.info(f"Played audio: {audio_path}")
        return True
    except FileNotFoundError:
        logger.warning("aplay not found - audio playback unavailable")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Audio playback timed out")
        return False
    except Exception as e:
        logger.error(f"Failed to play audio: {e}")
        return False


def handle_task_completion_event(
    task_name: str,
    action: str,
    minutes_spent: int = None,
    other_tasks: list = None,
    recommended_next: str = None
):
    """
    Handles a task completion event with audio feedback.

    Args:
        task_name: Name of the task
        action: Action taken (complete, paused, started, etc.)
        minutes_spent: Time spent on task
        other_tasks: List of remaining tasks
        recommended_next: Recommended next task

    Returns:
        bool: Success status
    """
    logger.info(f"Task event: {task_name} - {action}")

    # Map action to sound effect
    sound_effects = {
        "complete": "done.wav",
        "completed": "done.wav",
        "paused": "paused.wav",
        "pause": "paused.wav",
        "started": "started.wav",
        "start": "started.wav",
        "resumed": "started.wav",
        "resume": "started.wav",
        "error": "error.wav"
    }

    action_lower = action.lower()
    sound_file = sound_effects.get(action_lower, "started.wav")

    # Step 1: Play sound effect (ding/chime)
    logger.info(f"Playing sound effect: {sound_file}")
    if os.path.exists(sound_file):
        play_audio_file(sound_file)
    else:
        logger.warning(f"Sound effect not found: {sound_file}")

    # Step 2: Generate motivational TTS message
    logger.info("Generating AI-powered motivational message...")
    tts_path = f"/tmp/task_{action_lower}_{os.getpid()}.mp3"

    audio_path = worker_ai.generate_task_completion_audio(
        task_name=task_name,
        action=action,
        minutes_spent=minutes_spent,
        other_tasks=other_tasks,
        recommended_next=recommended_next,
        output_path=tts_path,
        speaker="luna"
    )

    if audio_path and os.path.exists(audio_path):
        logger.info(f"Generated TTS: {audio_path}")

        # Step 3: Play motivational message
        play_audio_file(audio_path)

        # Clean up temp file
        try:
            os.remove(audio_path)
        except:
            pass

        return True
    else:
        logger.error("Failed to generate TTS audio")
        return False


def example_task_completed():
    """Example: Task completed event."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Task Completed")
    print("="*70 + "\n")

    success = handle_task_completion_event(
        task_name="Write Documentation",
        action="completed",
        minutes_spent=45,
        other_tasks=[
            "Review Pull Request #123",
            "Update Unit Tests",
            "Deploy to Staging"
        ],
        recommended_next="Review Pull Request #123"
    )

    if success:
        print("✓ Task completion event handled successfully")
    else:
        print("✗ Task completion event failed")


def example_task_paused():
    """Example: Task paused event."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Task Paused")
    print("="*70 + "\n")

    success = handle_task_completion_event(
        task_name="Database Migration",
        action="paused",
        minutes_spent=30
    )

    if success:
        print("✓ Task paused event handled successfully")
    else:
        print("✗ Task paused event failed")


def example_task_started():
    """Example: Task started event."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Task Started")
    print("="*70 + "\n")

    success = handle_task_completion_event(
        task_name="Implement Feature X",
        action="started"
    )

    if success:
        print("✓ Task started event handled successfully")
    else:
        print("✗ Task started event failed")


def example_custom_message():
    """Example: Custom motivational message using generate_text."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Custom Motivational Message")
    print("="*70 + "\n")

    # Generate custom motivational message
    prompt = (
        "A developer just completed a complex debugging session that took 90 minutes. "
        "Write a brief, encouraging message (2-3 sentences) congratulating them and "
        "suggesting they take a short break before continuing with code review."
    )

    message = worker_ai.generate_text(
        prompt=prompt,
        system_prompt="You are a supportive productivity coach for software developers.",
        temperature=0.8,
        max_tokens=150
    )

    if message:
        print(f"Generated message:\n{message}\n")

        # Convert to speech
        audio_path = worker_ai.generate_voice(
            text=message,
            output_path="/tmp/custom_motivation.mp3",
            speaker="luna"
        )

        if audio_path:
            print(f"✓ Audio saved to: {audio_path}")
            play_audio_file(audio_path)
            try:
                os.remove(audio_path)
            except:
                pass
        else:
            print("✗ Failed to generate audio")
    else:
        print("✗ Failed to generate message")


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("WORKER_AI HARDWARE INTEGRATION EXAMPLES")
    print("="*70)

    # Check for credentials
    has_creds = False
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"):
        has_creds = True
    elif os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        has_creds = True

    if not has_creds:
        print("\n⚠️  WARNING: Cloudflare credentials not found.")
        print("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN\n")
        return 1

    # Run examples
    try:
        example_task_completed()
        example_task_paused()
        example_task_started()
        example_custom_message()

        print("\n" + "="*70)
        print("All examples completed!")
        print("="*70 + "\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nError: {e}")
        logger.exception("Example failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
