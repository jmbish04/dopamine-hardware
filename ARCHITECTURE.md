# Dopamine Hardware Bridge - Architecture

## Overview

This repository contains a modular Python application that runs on a Raspberry Pi 4, acting as a hardware bridge between physical devices (thermal printer, barcode scanner) and the Onion Tasker Cloudflare Worker.

## System Architecture

### 3-Tier Fallback Communication Protocol

The bridge maintains three resilient communication channels with the Cloudflare Worker:

1. **Tier 1 (VPC Push)**: Flask server on `0.0.0.0:8080` exposed via Cloudflare Tunnel (`cloudflared`)
   - Worker makes direct HTTP POST requests to `/print` endpoint
   - Lowest latency, highest priority

2. **Tier 2 (WebSocket)**: Persistent WSS connection for pub/sub broadcasts
   - Background thread maintains connection to Worker's WebSocket endpoint
   - Automatic reconnection on disconnect

3. **Tier 3 (REST Polling)**: Fallback polling mechanism
   - Background thread polls Worker's `/api/printer/pending` every 15 seconds
   - Ensures no jobs are lost during network outages

## Module Structure

### `config.py`
**Purpose**: Central configuration constants
**Dependencies**: None
**Contents**:
- Hardware identifiers (Vendor ID, Product ID)
- Cloudflare Worker URLs (HTTP, WebSocket)
- File paths (SQLite database location)

### `core_logger.py`
**Purpose**: Logging infrastructure
**Dependencies**: None
**Contents**:
- `DualLoggerHandler`: Custom logging handler that queues logs for telemetry
- `log_queue`: Thread-safe queue for log entries
- `setup_logger()`: Initializes console and dual-output logging

### `telemetry.py`
**Purpose**: Telemetry collection and transmission
**Dependencies**: `core_logger`, `config`
**Contents**:
- `telemetry_worker()`: Background thread that:
  - Writes logs to local SQLite database
  - Pushes logs asynchronously to Cloudflare Worker telemetry endpoint
  - Ensures graceful failure if Worker is unreachable

### `audio.py`
**Purpose**: Audio synthesis and playback
**Dependencies**: None (system libraries: wave, subprocess)
**Contents**:
- `generate_sounds()`: Synthesizes WAV files for UI feedback
- `play_sound()`: Non-blocking audio playback via `aplay`

### `printer.py`
**Purpose**: Thermal printer interface (Epson TM-T20III)
**Dependencies**: `config`
**Contents**:
- `get_printer()`: USB printer initialization
- `print_and_ack()`: Thread-safe printing with job deduplication
- `printer_lock`: Threading lock to prevent USB bus collisions
- `_sanitize_escpos_input()`: Input validation and sanitization
- `_format_timestamp()`: Timestamp formatting helper

### `scanner.py`
**Purpose**: Barcode scanner interface (Tera D5100)
**Dependencies**: `config`, `audio`
**Contents**:
- `scanner_worker()`: Background thread monitoring evdev for barcode scans
- Supports generic HID keyboard devices
- Handles scan types (task vs. command) with audio feedback

### `cloud_sync.py`
**Purpose**: Cloudflare Worker communication
**Dependencies**: `config`, `printer`
**Contents**:
- `run_websocket()`: Maintains persistent WebSocket connection
  - Auto-reconnects on disconnect
  - Triggers `print_and_ack()` on incoming jobs
- `run_rest_polling()`: Fallback polling mechanism
  - Polls every 15 seconds for missed jobs
  - Resilient to temporary network failures

### `api.py`
**Purpose**: Flask REST API (VPC endpoints)
**Dependencies**: `printer`
**Contents**:
- `POST /print`: Primary print job endpoint
- `GET|POST /test`: Hardware diagnostic endpoint (prints test receipt)
- `GET /logs?lines=N`: Returns systemd journal logs

### `ai/` Package
**Purpose**: Cloudflare AI integration for text generation and TTS
**Dependencies**: openai, requests
**Sub-modules**:
- `ai/config.py`: Configuration and environment helpers
- `ai/text.py`: Text and structured response generation
- `ai/speech.py`: Text-to-speech and audio generation
- `ai/diagnostics.py`: Hardware diagnostics using AI
- `ai/__init__.py`: Package initialization

**Key Functions**:
- `generate_text()`: LLM text generation
- `generate_structured_response()`: JSON-structured responses
- `generate_voice()`: Text-to-speech synthesis
- `generate_task_completion_audio()`: Task event audio with motivational messages
- `diagnose_hardware()`: AI-powered hardware configuration analysis

### `main.py`
**Purpose**: Application entry point
**Dependencies**: All modules
**Contents**:
- Initializes logging via `setup_logger()`
- Spawns daemon threads for:
  - Telemetry worker
  - Scanner worker
  - WebSocket connection
  - REST polling
- Starts Flask server on `0.0.0.0:8080`

## Deployment

### SystemD Service

The application is managed by `dopamine.service`:

```ini
[Unit]
Description=Dopamine Hardware Bridge
After=network.target

[Service]
User=hacolby
WorkingDirectory=/home/pi/dopamine-hardware
ExecStart=/home/pi/dopamine-hardware/.venv/bin/python main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Installation

```bash
# Install Python dependencies
cd /home/pi/dopamine-hardware
source .venv/bin/activate
pip install -r requirements.txt

# Enable and start service
sudo systemctl enable /home/pi/dopamine-hardware/dopamine.service
sudo systemctl start dopamine.service

# View logs
journalctl -u dopamine.service -f
```

## Thread Safety

### Critical Sections

The `printer_lock` (threading.Lock) protects:
- USB printer access in `print_and_ack()`
- Prevents race conditions between VPC, WebSocket, and REST threads
- All three communication tiers can trigger prints simultaneously

### Shared State

- `printed_jobs` (set): Tracks completed job IDs to prevent duplicates
  - Protected by `printer_lock`
  - Shared across all communication tiers

## Hardware Requirements

- **Raspberry Pi 4**: Debian/Raspberry Pi OS Lite 64-bit
- **Printer**: Epson TM-T20III (USB Vendor `04b8`, Product `0e28`)
- **Scanner**: Tera D5100 2D Barcode Scanner (USB HID Keyboard)
- **Audio**: ALSA-compatible audio output for beep feedback

## Development Notes

### Why This Structure?

The original monolithic `app.py` combined all functionality in a single 365-line file. This refactoring provides:

1. **Separation of Concerns**: Each module has a single, well-defined purpose
2. **Thread Safety**: Clear boundaries prevent race conditions
3. **Testability**: Modules can be tested independently
4. **Maintainability**: Changes to one domain don't affect others
5. **Resilience**: Failures in one subsystem don't cascade

### Import Chain

```
config.py (no dependencies)
├── core_logger.py (no dependencies)
│   └── telemetry.py
│       └── main.py
├── audio.py (no dependencies)
├── printer.py
│   ├── cloud_sync.py
│   │   └── main.py
│   └── api.py
│       └── main.py
├── scanner.py (depends on audio)
│   └── main.py
└── ai/ package (no cross-dependencies with hardware)
    ├── ai/config.py (no dependencies)
    ├── ai/text.py (depends on ai/config)
    ├── ai/speech.py (depends on ai/config, ai/text)
    └── ai/diagnostics.py (depends on ai/text)
```

No circular dependencies exist. All modules import cleanly.

### Legacy Compatibility

The original `app.py` is preserved for reference and rollback purposes.
The original monolithic `hardware.py` has been split into `audio.py`, `printer.py`, and `scanner.py`.
The original `worker_ai.py` has been refactored into the `ai/` package for better modularity.
The systemd service points to `main.py`.

## Monitoring

### Telemetry Flow

```
Application Code
    ↓
DualLoggerHandler
    ↓
log_queue (thread-safe)
    ↓
telemetry_worker() thread
    ├→ Local SQLite (/home/pi/dopamine-hardware/dopamine_logs.db)
    └→ Cloudflare Worker (/api/printer/telemetry)
```

### Key Metrics

- Printer connection status
- Scanner connection status
- Network connectivity (via diagnostic endpoint)
- Job completion acknowledgments
- Error rates and types

## Security Considerations

- **No Secrets in Code**: All credentials managed via Cloudflare Tunnel
- **Localhost Binding**: Flask binds to `0.0.0.0` but only accessible via Cloudflare Tunnel
- **Input Validation**: All print jobs validated before hardware interaction
- **USB Device Allowlisting**: Only approved Vendor/Product IDs accepted

## Future Enhancements

- [ ] Add unit tests for each module
- [ ] Implement metrics dashboard
- [ ] Support multiple printer models
- [ ] Add barcode validation/parsing logic
- [ ] Implement job prioritization
- [ ] Add remote configuration updates
