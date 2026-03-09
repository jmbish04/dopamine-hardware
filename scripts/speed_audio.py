#!/usr/bin/env python3
"""
Fallback utility to adjust audio playback speed using sox or ffmpeg.

This script is used when Cloudflare Workers AI rejects the 'speed' parameter
in the TTS API request. It post-processes the downloaded MP3 files to adjust
their playback speed.

Usage:
    python scripts/speed_audio.py input.mp3 output.mp3 1.3
    python scripts/speed_audio.py input.mp3 output.mp3 1.2

Dependencies:
    - sox (preferred): sudo apt-get install sox libsox-fmt-all
    - ffmpeg (fallback): sudo apt-get install ffmpeg
"""

import sys
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None


def speed_up_audio_sox(input_path: str, output_path: str, speed: float) -> bool:
    """
    Adjust audio speed using sox (Sound eXchange).

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        speed: Speed multiplier (e.g., 1.2, 1.3)

    Returns:
        True if successful, False otherwise
    """
    try:
        # sox input.mp3 output.mp3 tempo <speed>
        # tempo preserves pitch while changing speed
        cmd = ["sox", input_path, output_path, "tempo", str(speed)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            logger.info(f"Successfully adjusted audio speed to {speed}x using sox")
            return True
        else:
            logger.error(f"sox failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("sox command timed out")
        return False
    except Exception as e:
        logger.error(f"Error running sox: {e}")
        return False


def speed_up_audio_ffmpeg(input_path: str, output_path: str, speed: float) -> bool:
    """
    Adjust audio speed using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        speed: Speed multiplier (e.g., 1.2, 1.3)

    Returns:
        True if successful, False otherwise
    """
    try:
        # ffmpeg -i input.mp3 -filter:a "atempo=<speed>" -vn output.mp3
        # atempo filter changes speed while preserving pitch
        # Note: atempo only supports values between 0.5 and 2.0
        if speed < 0.5 or speed > 2.0:
            logger.error(f"ffmpeg atempo only supports speed between 0.5 and 2.0, got {speed}")
            return False

        cmd = [
            "ffmpeg", "-y",  # Overwrite output file
            "-i", input_path,
            "-filter:a", f"atempo={speed}",
            "-vn",  # No video
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            logger.info(f"Successfully adjusted audio speed to {speed}x using ffmpeg")
            return True
        else:
            logger.error(f"ffmpeg failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg command timed out")
        return False
    except Exception as e:
        logger.error(f"Error running ffmpeg: {e}")
        return False


def adjust_audio_speed(input_path: str, output_path: str, speed: float = 1.0) -> bool:
    """
    Adjust audio playback speed using available tools.

    Tries sox first (preferred), then falls back to ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        speed: Speed multiplier (e.g., 1.2 for 20% faster, 1.3 for 30% faster)

    Returns:
        True if successful, False otherwise
    """
    # Validate inputs
    if not Path(input_path).exists():
        logger.error(f"Input file does not exist: {input_path}")
        return False

    if speed <= 0:
        logger.error(f"Speed must be positive, got {speed}")
        return False

    if speed == 1.0:
        # No speed adjustment needed, just copy the file
        try:
            shutil.copy2(input_path, output_path)
            logger.info("Speed is 1.0, copied file without modification")
            return True
        except Exception as e:
            logger.error(f"Failed to copy file: {e}")
            return False

    # Try sox first (preferred)
    if check_command_exists("sox"):
        logger.info("Using sox for audio speed adjustment")
        return speed_up_audio_sox(input_path, output_path, speed)

    # Fall back to ffmpeg
    if check_command_exists("ffmpeg"):
        logger.info("Using ffmpeg for audio speed adjustment")
        return speed_up_audio_ffmpeg(input_path, output_path, speed)

    logger.error("Neither sox nor ffmpeg found. Please install one of them:")
    logger.error("  - sox: sudo apt-get install sox libsox-fmt-all")
    logger.error("  - ffmpeg: sudo apt-get install ffmpeg")
    return False


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if len(sys.argv) != 4:
        print("Usage: python scripts/speed_audio.py <input.mp3> <output.mp3> <speed>")
        print("Example: python scripts/speed_audio.py /tmp/audio.mp3 /tmp/audio_fast.mp3 1.3")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        speed = float(sys.argv[3])
    except ValueError:
        print(f"Error: Speed must be a number, got '{sys.argv[3]}'")
        sys.exit(1)

    success = adjust_audio_speed(input_path, output_path, speed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
