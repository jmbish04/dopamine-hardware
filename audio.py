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
import time

logger = logging.getLogger(__name__)

# Thread lock for audio playback to prevent overlapping audio
audio_lock = threading.Lock()

def _get_media_players():
    """
    Get list of active media players via D-Bus MPRIS2 interface.

    Returns:
        list: List of player names (e.g., ['spotify', 'vlc'])
    """
    try:
        result = subprocess.run(
            ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus",
             "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode != 0:
            return []

        # Parse output for MPRIS2 players (org.mpris.MediaPlayer2.*)
        players = []
        for line in result.stdout.split('\n'):
            if 'org.mpris.MediaPlayer2.' in line:
                # Extract player name (e.g., "org.mpris.MediaPlayer2.spotify" -> "spotify")
                player = line.split('org.mpris.MediaPlayer2.')[-1].strip('" ')
                if player:
                    players.append(player)
        return players
    except Exception as e:
        logger.debug(f"Failed to get media players: {e}")
        return []

def _get_player_status(player):
    """
    Get playback status of a media player.

    Args:
        player: Player name (e.g., 'spotify')

    Returns:
        str: 'Playing', 'Paused', 'Stopped', or None if unknown
    """
    try:
        result = subprocess.run(
            ["dbus-send", "--session", "--print-reply",
             f"--dest=org.mpris.MediaPlayer2.{player}",
             "/org/mpris/MediaPlayer2",
             "org.freedesktop.DBus.Properties.Get",
             "string:org.mpris.MediaPlayer2.Player",
             "string:PlaybackStatus"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse output like: variant       string "Playing"
            for line in result.stdout.split('\n'):
                # More robustly parse 'string "Playing"'
                clean_line = line.strip()
                if clean_line.startswith('string "'):
                    status = clean_line.split('"')[1]
                    if status in ('Playing', 'Paused', 'Stopped'):
                        return status
        return None
    except Exception as e:
        logger.debug(f"Failed to get player status for {player}: {e}")
        return None

def _pause_player(player):
    """
    Pause a media player via D-Bus MPRIS2.

    Args:
        player: Player name (e.g., 'spotify')

    Returns:
        bool: True if successfully paused
    """
    try:
        result = subprocess.run(
            ["dbus-send", "--session", "--print-reply",
             f"--dest=org.mpris.MediaPlayer2.{player}",
             "/org/mpris/MediaPlayer2",
             "org.mpris.MediaPlayer2.Player.Pause"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            logger.info(f"Paused media player: {player}")
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to pause {player}: {e}")
        return False

def _play_player(player):
    """
    Resume/play a media player via D-Bus MPRIS2.

    Args:
        player: Player name (e.g., 'spotify')

    Returns:
        bool: True if successfully resumed
    """
    try:
        result = subprocess.run(
            ["dbus-send", "--session", "--print-reply",
             f"--dest=org.mpris.MediaPlayer2.{player}",
             "/org/mpris/MediaPlayer2",
             "org.mpris.MediaPlayer2.Player.Play"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            logger.info(f"Resumed media player: {player}")
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to resume {player}: {e}")
        return False

def _pause_active_media():
    """
    Pause all currently playing media players.

    Returns:
        list: List of player names that were paused
    """
    paused_players = []
    players = _get_media_players()

    for player in players:
        status = _get_player_status(player)
        if status == 'Playing':
            if _pause_player(player):
                paused_players.append(player)
                # Give the player a moment to release the audio device
                time.sleep(0.3)

    return paused_players

def _resume_media(players):
    """
    Resume previously paused media players.

    Args:
        players: List of player names to resume
    """
    for player in players:
        _play_player(player)
        # Small delay between resuming multiple players
        if len(players) > 1:
            time.sleep(0.1)

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

    Automatically pauses any playing media (Spotify, VLC, etc.) before playback
    and resumes them after completion.

    Args:
        audio_path: Path to audio file (.mp3 or .wav)

    Returns:
        bool: True if playback succeeded, False otherwise
    """
    with audio_lock:
        # Pause any active media players before playing audio
        paused_players = _pause_active_media()
        if paused_players:
            logger.info(f"Paused media players for speech: {', '.join(paused_players)}")

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
        finally:
            # Always resume paused media players after playback (success or failure)
            if paused_players:
                logger.info(f"Resuming media players: {', '.join(paused_players)}")
                _resume_media(paused_players)
