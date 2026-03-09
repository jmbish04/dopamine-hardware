# Audio Speed Adjustment Fallback

## Overview

The Cloudflare Workers AI TTS API for `@cf/deepgram/aura-2-en` officially supports the following parameters:
- `text` (required)
- `speaker`
- `encoding`
- `container`
- `sample_rate`
- `bit_rate`

**Note:** The `speed` parameter is **NOT** officially supported in the Cloudflare Workers AI schema, though it is supported by Deepgram's native API. If Cloudflare's API gateway rejects requests with the `speed` parameter (HTTP 400 with schema validation errors), you'll need to use the fallback script to adjust audio speed post-download.

## Fallback Script Usage

The `scripts/speed_audio.py` script provides a fallback mechanism to adjust audio playback speed using local utilities.

### Prerequisites

Install either `sox` (preferred) or `ffmpeg`:

```bash
# Option 1: sox (preferred - better quality for speech)
sudo apt-get install sox libsox-fmt-all

# Option 2: ffmpeg (alternative)
sudo apt-get install ffmpeg
```

### Command Line Usage

```bash
# Basic usage
python3 scripts/speed_audio.py <input.mp3> <output.mp3> <speed>

# Example: Speed up audio by 30% (1.3x)
python3 scripts/speed_audio.py /tmp/task_1.mp3 /tmp/task_1_fast.mp3 1.3

# Example: Speed up audio by 20% (1.2x)
python3 scripts/speed_audio.py /tmp/motivation.mp3 /tmp/motivation_fast.mp3 1.2
```

### Programmatic Usage

If you need to modify the code to use the fallback script instead of passing `speed` to the API:

```python
from scripts.speed_audio import adjust_audio_speed

# In ai/speech.py, modify generate_voice():
def generate_voice(
    text: str,
    output_path: str = "output.mp3",
    speaker: str = "luna",
    speed: float = 1.0
) -> Optional[str]:
    try:
        safe_output_path = sanitize_output_path(output_path)
        config = get_config()

        # ... existing code ...

        # Remove 'speed' from payload if Cloudflare rejects it
        payload = {
            "text": text,
            "speaker": speaker
            # "speed": speed  # REMOVE THIS LINE
        }

        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)

        if response.status_code == 200:
            # Save to temporary file first
            temp_path = safe_output_path + ".tmp"
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Apply speed adjustment if needed
            if speed != 1.0:
                from scripts.speed_audio import adjust_audio_speed
                if adjust_audio_speed(temp_path, safe_output_path, speed):
                    os.remove(temp_path)
                    logger.info(f"Audio saved with {speed}x speed to {safe_output_path}")
                    return safe_output_path
                else:
                    # Fallback: use original speed
                    shutil.move(temp_path, safe_output_path)
                    logger.warning(f"Speed adjustment failed, using original audio")
                    return safe_output_path
            else:
                shutil.move(temp_path, safe_output_path)
                return safe_output_path
        # ... rest of error handling ...
```

## Testing the Implementation

### Test if Cloudflare accepts the speed parameter:

```bash
# Set your credentials
export CF_ACCOUNT_ID="your-account-id"
export CF_API_TOKEN="your-api-token"

# Run a simple test
cd /home/runner/work/dopamine-hardware/dopamine-hardware
python3 << 'EOF'
from ai.speech import generate_voice
result = generate_voice("Test message", "/tmp/test_audio.mp3", speaker="athena", speed=1.3)
if result:
    print(f"SUCCESS: Audio generated at {result}")
else:
    print("FAILED: Check logs for API rejection errors")
EOF
```

### If the test fails with a 400 error mentioning unknown field "speed":

1. Remove the `speed` parameter from the payload in `ai/speech.py`
2. Integrate the fallback script as shown in the "Programmatic Usage" section above
3. Rerun the test

## Current Implementation Status

As of this commit, the code **includes** the `speed` parameter in the API payload. Based on the Cloudflare documentation, this may be:
- **Silently ignored** by Cloudflare (best case - API accepts it but doesn't apply it)
- **Rejected** with a 400 Bad Request (needs fallback implementation)
- **Accepted and applied** (ideal case, though undocumented)

Monitor the logs after deployment to see how Cloudflare handles the parameter.

## References

- [Cloudflare Workers AI - aura-2-en Documentation](https://developers.cloudflare.com/workers-ai/models/aura-2-en/)
- [Deepgram Aura TTS API](https://developers.deepgram.com/docs/tts-models) (native API supports speed)
- [Sox Documentation](http://sox.sourceforge.net/sox.html)
- [FFmpeg atempo Filter](https://ffmpeg.org/ffmpeg-filters.html#atempo)
