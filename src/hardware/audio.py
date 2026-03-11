"""
Audio synthesis and playback module for UI feedback.
Generates WAV files for different event types and plays them via ALSA.
"""
import wave
import struct
import math
import subprocess
import os
import logging
import threading

logger = logging.getLogger(__name__)

# Thread lock for audio playback to prevent overlapping audio
audio_lock = threading.Lock()

def generate_sounds():
    """Synthesizes complex 16-bit melodies for UI feedback."""
    def make_melody(filename, notes):
        if os.path.exists(filename): return
        sample_rate = 44100
        with wave.open(filename, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            for freq, duration in notes:
                # Play the note for 85% of the duration, and silence for 15%
                # This creates that distinct "staccato" separation between notes
                note_samples = int(sample_rate * (duration * 0.85))
                rest_samples = int(sample_rate * (duration * 0.15))

                for i in range(note_samples):
                    val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                    f.writeframesraw(struct.pack('<h', val))
                for i in range(rest_samples):
                    f.writeframesraw(struct.pack('<h', 0))

    # 1. PLAY: A quick, ascending double-chime (Booting up)
    make_melody('started.wav', [(440.0, 0.1), (659.25, 0.2)]) # A4 -> E5

    # 2. PAUSE: A descending double-chime (Powering down)
    make_melody('paused.wav', [(659.25, 0.1), (440.0, 0.2)])  # E5 -> A4

    # 3. DONE: The Antigravity "Dah Dah Dah DAAHHH" Success Fanfare
    make_melody('done.wav', [
        (523.25, 0.15),
        (523.25, 0.15),
        (523.25, 0.15),
        (880.00, 0.5)
    ])

    # 4. ERROR: Two harsh, low buzzes
    make_melody('error.wav', [(150.0, 0.2), (150.0, 0.3)])

# Generate sounds on module import
generate_sounds()

def play_sound(action_type):
    """Plays the specific sound without blocking the thread, ignoring missing hardware errors."""
    files = {
        "play": "started.wav",
        "pause": "paused.wav",
        "done": "done.wav",
        "error": "error.wav"
    }
    file = files.get(action_type, "started.wav")
    # Force audio through Card 3 (Logitech USB) using the plughw translator
    subprocess.Popen(['aplay', '-D', 'plughw:3,0', '-q', file], stderr=subprocess.DEVNULL)

def play_audio_file(audio_path):
    """
    Plays an audio file using ffmpeg (to decode mp3) and aplay (for wav) with thread safety.
    Bypasses mpg123 ALSA driver issues by securely piping WAV data in memory.

    Args:
        audio_path: Path to audio file (.mp3 or .wav)

    Returns:
        bool: True if playback succeeded, False otherwise
    """
    with audio_lock:
        try:
            if audio_path.lower().endswith('.mp3'):
                # Pipe ffmpeg stdout (wav data) to aplay stdin
                ffmpeg_proc = subprocess.Popen(
                    ["ffmpeg", "-v", "quiet", "-i", audio_path, "-f", "wav", "-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                aplay_proc = subprocess.Popen(
                    ["aplay", "-D", "plughw:3,0", "-q"],
                    stdin=ffmpeg_proc.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Close ffmpeg stdout in parent so it receives SIGPIPE if aplay exits early
                ffmpeg_proc.stdout.close()
                
                # Wait for aplay to finish
                _, aplay_err = aplay_proc.communicate(timeout=30)
                ffmpeg_proc.wait(timeout=30)
                
                if aplay_proc.returncode != 0:
                    logger.error(f"Failed to play audio (aplay error): {aplay_err.decode('utf-8', errors='ignore').strip()}")
                    return False
                    
                logger.info(f"Played audio via ffmpeg pipeline: {audio_path}")
                return True
            else:
                # It's already a WAV file
                subprocess.run(
                    ["aplay", "-D", "plughw:3,0", "-q", audio_path],
                    check=True,
                    capture_output=True,
                    timeout=30
                )
                logger.info(f"Played audio: {audio_path}")
                return True
                
        except FileNotFoundError:
            missing_bin = "ffmpeg" if audio_path.lower().endswith('.mp3') else "aplay"
            logger.warning(f"'{missing_bin}' not found - run 'sudo apt-get install {missing_bin} -y'")
            return False
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore').strip() if e.stderr else str(e)
            logger.error(f"Failed to play audio (aplay error): {error_msg}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Audio playback timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
            return False
