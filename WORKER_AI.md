# Worker AI Module

AI-powered capabilities for the Dopamine Hardware Bridge using Cloudflare Workers AI and AI Gateway.

## Overview

The `worker_ai.py` module provides three core AI functions:

1. **Text Generation** (`generate_text`) - General-purpose text generation using Cloudflare AI Gateway
2. **Structured Responses** (`generate_structured_response`) - JSON-formatted responses with schema validation
3. **Text-to-Speech** (`generate_voice`) - Audio synthesis using Deepgram Aura-2 via Cloudflare Workers AI

Additionally, it includes specialized functions for:
- **Task Completion Audio** (`generate_task_completion_audio`) - Context-aware motivational messages for task events
- **Hardware Diagnostics** (`diagnose_hardware`) - AI-powered hardware configuration validation

## Environment Variables

Set these environment variables before using the module:

```bash
# Required (use either set)
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token

# Or alternative names:
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token

# Optional
CF_GATEWAY_NAME=default-gateway  # Default: "default-gateway"
```

## Installation

The module requires these dependencies (already in `requirements.txt`):

```bash
pip install openai requests python-dotenv
```

## Usage Examples

### 1. Text Generation

```python
import worker_ai

text = worker_ai.generate_text(
    prompt="What is edge computing?",
    temperature=0.7,
    max_tokens=200
)
print(text)
```

### 2. Structured JSON Response

```python
import worker_ai

schema = {
    "task_name": "string",
    "priority": "string - high/medium/low",
    "estimated_minutes": "number"
}

result = worker_ai.generate_structured_response(
    prompt="Create a task for API documentation",
    json_schema=schema,
    temperature=0.3
)
print(result)  # Returns parsed JSON dict
```

### 3. Text-to-Speech

```python
import worker_ai

audio_path = worker_ai.generate_voice(
    text="The hardware bridge is operational.",
    output_path="output.mp3",
    speaker="luna"  # Options: luna, hermes, vesta, thalia, etc.
)
# Audio saved to output.mp3
```

### 4. Task Completion Audio (Context-Aware)

```python
import worker_ai

audio_path = worker_ai.generate_task_completion_audio(
    task_name="Write Documentation",
    action="completed",
    minutes_spent=45,
    other_tasks=["Review PR", "Deploy"],
    recommended_next="Review PR",
    output_path="task_done.mp3",
    speaker="luna"
)
# Generates: "Congratulations on completing 'Write Documentation' after 45 minutes!
# Great work staying focused. Next, I recommend reviewing the pull request..."
```

The function generates context-aware messages:
- **Completed tasks**: Celebratory with recommendations for next task
- **Paused tasks**: Encouraging with focus tips
- **Started tasks**: Motivating to help concentration

Remember to play the appropriate sound effect first:
- `done.wav` for completed tasks
- `paused.wav` for paused tasks
- `started.wav` for started/resumed tasks

### 5. Hardware Diagnostics

```python
import worker_ai
import subprocess

lsusb_output = subprocess.check_output("lsusb", text=True)
udev_rules = open("/etc/udev/rules.d/99-escpos.rules").read()
app_code = open("hardware.py").read()

result = worker_ai.diagnose_hardware(
    lsusb_output=lsusb_output,
    udev_rules=udev_rules,
    app_code=app_code
)

print(result["analysis"])
if result["mismatch_found"]:
    print(result["required_modifications"])
```

## Testing

Run the comprehensive test suite:

```bash
# Set credentials first
export CLOUDFLARE_ACCOUNT_ID=your_account_id
export CLOUDFLARE_API_TOKEN=your_api_token

# Run tests
python3 scripts/test_worker_ai.py
```

Run integration examples:

```bash
python3 scripts/example_task_audio.py
```

## Integration with Hardware

Example integration with the existing `hardware.py` module:

```python
import worker_ai
from hardware import play_sound

def handle_task_event(task_name, action, minutes=None):
    # Play sound effect
    play_sound(action)

    # Generate and play AI message
    audio = worker_ai.generate_task_completion_audio(
        task_name=task_name,
        action=action,
        minutes_spent=minutes,
        output_path="/tmp/task_msg.mp3"
    )

    if audio:
        # Play using aplay (Raspberry Pi)
        import subprocess
        import os
        subprocess.run(["aplay", "-q", audio])
        os.remove(audio)
```

## API Reference

### `generate_text(prompt, model, temperature, max_tokens, system_prompt)`

Generate text using Cloudflare AI Gateway.

**Parameters:**
- `prompt` (str): The user prompt/question
- `model` (str): Model to use (default: `workers-ai/@cf/openai/gpt-oss-120b`)
- `temperature` (float): Response creativity 0.0-1.0 (default: 0.7)
- `max_tokens` (int): Maximum response length (default: 1024)
- `system_prompt` (str, optional): System instruction

**Returns:** `str | None` - Generated text or None on failure

---

### `generate_structured_response(prompt, json_schema, model, temperature, max_tokens, system_prompt)`

Generate a structured JSON response.

**Parameters:**
- `prompt` (str): The user prompt/question
- `json_schema` (dict, optional): Expected JSON schema description
- `model` (str): Model to use (default: `workers-ai/@cf/openai/gpt-oss-120b`)
- `temperature` (float): Response creativity (default: 0.2)
- `max_tokens` (int): Maximum response length (default: 2048)
- `system_prompt` (str, optional): System instruction

**Returns:** `dict | None` - Parsed JSON dictionary or None on failure

---

### `generate_voice(text, output_path, speaker, encoding)`

Generate text-to-speech audio using Deepgram Aura-2.

**Parameters:**
- `text` (str): Text to synthesize
- `output_path` (str): Where to save audio (default: "output.mp3")
- `speaker` (str): Voice to use (default: "luna")
- `encoding` (str): Audio format (default: "mp3")

**Available Speakers:** luna, hermes, vesta, thalia, perseus, aura, angus, brian, stella, orpheus, helios, zeus, athena, hera, artemis, demeter, ares, hephaestus, aphrodite, apollo, poseidon

**Returns:** `str | None` - Path to audio file or None on failure

---

### `generate_task_completion_audio(task_name, action, minutes_spent, other_tasks, recommended_next, output_path, speaker)`

Generate context-aware motivational audio for task events.

**Parameters:**
- `task_name` (str): Name of the task
- `action` (str): Action taken (complete, paused, started, etc.)
- `minutes_spent` (int, optional): Time spent on task
- `other_tasks` (list, optional): List of remaining tasks
- `recommended_next` (str, optional): AI recommendation for next task
- `output_path` (str): Where to save audio (default: "task_completion.mp3")
- `speaker` (str): Voice to use (default: "luna")

**Returns:** `str | None` - Path to audio file or None on failure

---

### `diagnose_hardware(lsusb_output, udev_rules, app_code, model)`

AI-powered hardware configuration diagnostics.

**Parameters:**
- `lsusb_output` (str): Output from lsusb command
- `udev_rules` (str): Contents of udev rules file
- `app_code` (str): Hardware configuration code
- `model` (str): AI model to use (default: `workers-ai/@cf/openai/gpt-oss-120b`)

**Returns:** `dict | None` - Diagnostic results with keys: `analysis`, `mismatch_found`, `required_modifications`

## Architecture

The module follows the repository's architectural patterns:

- **Zero circular dependencies**: Only imports from `config.py` and standard library
- **Graceful error handling**: All API calls wrapped in try/except with logging
- **Thread-safe**: No shared mutable state
- **Environment-based config**: All credentials from environment variables
- **Comprehensive logging**: Uses Python's `logging` module

## Model Selection

Default model: `workers-ai/@cf/openai/gpt-oss-120b` (120B parameter GPT model)

Other available models via Cloudflare Workers AI:
- `@cf/meta/llama-3.1-8b-instruct`
- `@cf/mistral/mistral-7b-instruct-v0.1`
- `@cf/google/gemma-7b-it`

For TTS, the module uses `@cf/deepgram/aura-2-en` exclusively.

## Error Handling

All functions return `None` on failure and log errors. Check logs for details:

```python
import logging
logging.basicConfig(level=logging.INFO)

result = worker_ai.generate_text("prompt")
if result is None:
    print("Generation failed - check logs")
```

## Performance Notes

- **Text generation**: ~1-3 seconds (depends on token count)
- **TTS generation**: ~2-5 seconds (depends on text length)
- **Streaming**: TTS uses chunked streaming for efficiency
- **Caching**: Cloudflare AI Gateway provides automatic caching

## Troubleshooting

**"Missing Cloudflare credentials" error:**
```bash
export CLOUDFLARE_ACCOUNT_ID=your_account_id
export CLOUDFLARE_API_TOKEN=your_api_token
```

**"Failed to parse JSON response":**
- Increase `temperature` to 0.1 for more deterministic output
- Provide clearer schema description in `json_schema` parameter

**TTS audio not playing:**
- Check that `aplay` is installed: `which aplay`
- Verify audio hardware: `aplay -l`
- Test file manually: `aplay output.mp3`

**AI Gateway 403/401 errors:**
- Verify API token has Workers AI permissions
- Check account ID matches the token's account
- Ensure AI Gateway is enabled in your Cloudflare account

## License

Part of the dopamine-hardware project.
