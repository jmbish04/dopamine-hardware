# Dopamine Hardware Bridge - Architecture

## Overview

This repository contains a modular Python application that runs on a Raspberry Pi 4, acting as a hardware bridge between physical devices (thermal printer, barcode scanner) and the Onion Tasker Cloudflare Worker.

**Version 2.0** introduces a completely refactored modular structure with all modules organized in the `src/` directory.

## System Architecture

### 3-Tier Fallback Communication Protocol

The bridge maintains three resilient communication channels with the Cloudflare Worker:

1. **Tier 1 (VPC Push)**: Flask server on `0.0.0.0:8080` exposed via Cloudflare Tunnel (`cloudflared`)
   - Worker makes direct HTTP POST requests to `/print` endpoint
   - Lowest latency, highest priority

2. **Tier 2 (WebSocket)**: Persistent WSS connection for pub/sub broadcasts
   - Background thread maintains connection to Worker's WebSocket endpoint
   - **NEW**: Application-level heartbeat every 45 seconds to keep Cloudflare tunnel alive
   - **NEW**: Graceful handling of expected Cloudflare disconnects
   - Automatic reconnection on disconnect

3. **Tier 3 (REST Polling)**: Fallback polling mechanism
   - Background thread polls Worker's `/api/printer/pending` every 15 seconds
   - Ensures no jobs are lost during network outages

## Module Structure (v2.0)

All modules are now organized under the `src/` directory with clear separation of concerns:

### `src/core/` - Core Utilities

#### `src/core/config.py`
**Purpose**: Central configuration constants
**Dependencies**: None
**Contents**:
- Hardware identifiers (Vendor ID, Product ID)
- Cloudflare Worker URLs (HTTP, WebSocket)
- File paths (SQLite database location)

#### `src/core/core_logger.py`
**Purpose**: Logging infrastructure
**Dependencies**: None
**Contents**:
- `DualLoggerHandler`: Custom logging handler that queues logs for telemetry
- `log_queue`: Thread-safe queue for log entries
- `setup_logger()`: Initializes console and dual-output logging

#### `src/core/telemetry.py`
**Purpose**: Telemetry collection and transmission
**Dependencies**: `src.core.core_logger`, `src.core.config`
**Contents**:
- `telemetry_worker()`: Background thread that:
  - Writes logs to local SQLite database
  - Pushes logs asynchronously to Cloudflare Worker telemetry endpoint
  - Ensures graceful failure if Worker is unreachable

### `src/hardware/` - Hardware Interfaces

#### `src/hardware/audio.py`
**Purpose**: Audio synthesis and playback
**Dependencies**: None (system libraries: wave, subprocess)
**Contents**:
- `generate_sounds()`: Synthesizes WAV files for UI feedback
- `play_sound()`: Non-blocking audio playback via `aplay`

#### `src/hardware/printer.py`
**Purpose**: Thermal printer interface (Epson TM-T20III)
**Dependencies**: `src.core.config`
**Contents**:
- `get_printer()`: USB printer initialization
- `print_and_ack()`: Thread-safe printing with job deduplication
- `printer_lock`: Threading lock to prevent USB bus collisions
- `_sanitize_escpos_input()`: Input validation and sanitization
- `_format_timestamp()`: Timestamp formatting helper

#### `src/hardware/scanner.py`
**Purpose**: Barcode scanner interface (Tera D5100)
**Dependencies**: `src.core.config`, `src.hardware.audio`
**Contents**:
- `scanner_worker()`: Background thread monitoring evdev for barcode scans
- Supports generic HID keyboard devices
- Handles scan types (task vs. command) with audio feedback

### `src/network/` - Network Communication

#### `src/network/cloud_sync.py`
**Purpose**: Cloudflare Worker communication
**Dependencies**: `src.core.config`, `src.hardware.printer`
**Contents**:
- `run_websocket()`: Maintains persistent WebSocket connection
  - **NEW**: Application-level heartbeat every 45 seconds
  - **NEW**: Graceful handling of `WebSocketConnectionClosedException`, `WebSocketTimeoutException`, `ConnectionResetError`
  - **NEW**: Logs expected disconnects as INFO instead of ERROR
  - **NEW**: Tracks reconnection count for telemetry
  - Auto-reconnects on disconnect
  - Triggers `print_and_ack()` on incoming jobs
- `run_rest_polling()`: Fallback polling mechanism
  - Polls every 15 seconds for missed jobs
  - Resilient to temporary network failures

### `src/api/` - Flask REST API

#### `src/api/api.py`
**Purpose**: Flask REST API (VPC endpoints)
**Dependencies**: `src.hardware.printer`
**Contents**:
- `POST /print`: Primary print job endpoint
- `GET|POST /test`: Hardware diagnostic endpoint (prints test receipt)
- `GET /logs?lines=N`: Returns systemd journal logs

### `src/ai/` - Cloudflare AI Integration

**Purpose**: Cloudflare AI integration for text generation and TTS
**Dependencies**: openai, requests
**Sub-modules**:
- `src/ai/config.py`: Configuration and environment helpers
- `src/ai/text.py`: Text and structured response generation
- `src/ai/speech.py`: Text-to-speech and audio generation
- `src/ai/diagnostics.py`: Hardware diagnostics using AI
- `src/ai/__init__.py`: Package initialization

**Key Functions**:
- `generate_text()`: LLM text generation
- `generate_structured_response()`: JSON-structured responses
- `generate_voice()`: Text-to-speech synthesis
- `generate_task_completion_audio()`: Task event audio with motivational messages
- `diagnose_hardware()`: AI-powered hardware configuration analysis

## Main Entry Point

### `main.py`
**Purpose**: Application entry point
**Dependencies**: All modules
**Contents**:
- Initializes logging via `setup_logger()`
- Spawns daemon threads for:
  - Telemetry worker
  - Scanner worker
  - WebSocket connection (with heartbeat)
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

The original monolithic `app.py` combined all functionality in a single 365-line file. Version 2.0 provides:

1. **Separation of Concerns**: Each module has a single, well-defined purpose
2. **Clear Module Hierarchy**: Organized into logical packages (core, hardware, network, api, ai)
3. **Thread Safety**: Clear boundaries prevent race conditions
4. **Testability**: Modules can be tested independently
5. **Maintainability**: Changes to one domain don't affect others
6. **Resilience**: Failures in one subsystem don't cascade
7. **WebSocket Stability**: Application-level heartbeats prevent Cloudflare timeouts

### Import Chain (v2.0)

```
src/core/config.py (no dependencies)
├── src/core/core_logger.py (no dependencies)
│   └── src/core/telemetry.py
│       └── main.py
├── src/hardware/audio.py (no dependencies)
├── src/hardware/printer.py (depends on src.core.config)
│   ├── src/network/cloud_sync.py
│   │   └── main.py
│   └── src/api/api.py
│       └── main.py
├── src/hardware/scanner.py (depends on src.hardware.audio, src.core.config)
│   └── main.py
└── src/ai/ package (no cross-dependencies with hardware)
    ├── src/ai/config.py (no dependencies)
    ├── src/ai/text.py (depends on src.ai.config)
    ├── src/ai/speech.py (depends on src.ai.config, src.ai.text)
    └── src/ai/diagnostics.py (depends on src.ai.text)
```

No circular dependencies exist. All modules import cleanly.

### Legacy Compatibility

**Version 2.0** introduces a complete restructure into the `src/` directory:
- The original `app.py`, `audio.py`, `printer.py`, `scanner.py`, `cloud_sync.py`, `api.py`, `telemetry.py`, `core_logger.py`, `config.py` are preserved in the root for reference
- New modular structure in `src/` directory with improved imports
- The original monolithic `hardware.py` was split into `audio.py`, `printer.py`, and `scanner.py`
- The original `worker_ai.py` was refactored into the `ai/` package
- `main.py` now uses the modular `src/` imports
- The systemd service still points to `main.py` (no deployment changes required)

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
- **WebSocket reconnection count** (v2.0)
- **Application-level heartbeat status** (v2.0)
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
