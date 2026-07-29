# Spotify Pause/Resume for Speech Audio

## Problem
When Spotify (or other media players) are playing audio on the Raspberry Pi, the TTS speech audio fails with:
```
aplay: main:850: audio open error: Device or resource busy
```

This occurs because the audio device (`plughw:3,0`) is already in use by the media player.

## Solution
The `play_audio_file()` function in `src/hardware/audio.py` now automatically:
1. **Detects** active media players via D-Bus MPRIS2 interface
2. **Pauses** any playing media before starting speech playback
3. **Plays** the speech audio
4. **Resumes** the previously paused media after completion (even if playback fails)

## Implementation Details

### Media Player Detection
Uses D-Bus to query for MPRIS2-compliant media players:
- Spotify: `org.mpris.MediaPlayer2.spotify`
- VLC: `org.mpris.MediaPlayer2.vlc`
- Chrome/Firefox: `org.mpris.MediaPlayer2.chrome`, etc.

### Functions Added
- `_get_media_players()` - Lists all active MPRIS2 players
- `_get_player_status(player)` - Returns 'Playing', 'Paused', or 'Stopped'
- `_pause_player(player)` - Pauses a specific player
- `_play_player(player)` - Resumes a specific player
- `_pause_active_media()` - Pauses all currently playing players
- `_resume_media(players)` - Resumes a list of players

### Thread Safety
All pause/resume operations occur within the existing `audio_lock` context, ensuring:
- No race conditions between multiple audio requests
- Media players are properly resumed even if playback fails
- The `finally` block guarantees resume happens

### Timing
- **0.3 second delay** after pausing each player to allow audio device release
- **0.1 second delay** between resuming multiple players (if applicable)

## Usage
No code changes needed in other modules. The functionality is automatic:

```python
from src.hardware.audio import play_audio_file

# This will now automatically pause Spotify, play audio, and resume
play_audio_file("/tmp/task_completion.mp3")
```

## Requirements
- **D-Bus**: Already available on Raspberry Pi OS (`dbus-send` command)
- **MPRIS2**: Supported by Spotify, VLC, Chrome, Firefox, and most modern media players

## Logs
When media is paused/resumed, you'll see:
```
INFO - Paused media players for speech: spotify
INFO - Played audio via ffmpeg pipeline: /tmp/task_multi_2.mp3
INFO - Resuming media players: spotify
```

## Troubleshooting

### If media doesn't resume
- Check logs for D-Bus errors
- Verify Spotify supports MPRIS2: `dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep mpris`
- Test manually: `dbus-send --session --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Play`

### If pause fails
- All errors are logged but don't block playback
- If pause fails, the 0.3s delay still gives the device time to potentially free up
- The speech will attempt to play regardless

## Future Enhancements
- Add configuration to disable auto-pause via environment variable
- Support for players that don't implement MPRIS2 (use `lsof` on audio device)
- Configurable pause/resume delays
