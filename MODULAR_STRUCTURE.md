# Dopamine Hardware Bridge - Modular Structure

## 📁 New Directory Structure

```
dopamine-hardware/
├── src/                          # Main source code directory
│   ├── core/                     # Core utilities
│   │   ├── __init__.py
│   │   ├── config.py            # Configuration constants (URLs, device IDs, paths)
│   │   ├── core_logger.py       # Dual logging system (console + telemetry)
│   │   └── telemetry.py         # Log collection and transmission to Cloudflare
│   │
│   ├── hardware/                # Hardware interface modules
│   │   ├── __init__.py
│   │   ├── audio.py            # Audio synthesis and playback (beep sounds)
│   │   ├── printer.py          # Epson TM-T20III thermal printer interface
│   │   └── scanner.py          # Tera D5100 barcode scanner interface
│   │
│   ├── network/                # Network communication modules
│   │   ├── __init__.py
│   │   └── cloud_sync.py       # WebSocket + REST polling (with heartbeat fix)
│   │
│   ├── api/                    # Flask REST API
│   │   ├── __init__.py
│   │   ├── api.py              # API endpoints (/print, /test, /logs)
│   │   └── app.py              # Legacy Flask app (preserved for reference)
│   │
│   └── ai/                     # Cloudflare AI integration
│       ├── __init__.py
│       ├── config.py           # AI configuration and environment helpers
│       ├── text.py             # Text generation via Workers AI
│       ├── speech.py           # Text-to-speech synthesis
│       └── diagnostics.py      # Hardware diagnostics using AI
│
├── main.py                     # Application entry point
├── restart_fresh.sh           # Git pull + service restart + log streaming
├── dopamine.service           # SystemD service configuration
├── requirements.txt           # Python dependencies
└── *.wav                      # Audio feedback files (started, paused, done, error)
```

## 🔧 Key Improvements

### 1. **Modular Structure**
- **Before**: All code scattered in root directory
- **After**: Organized into logical modules (core, hardware, network, api, ai)

### 2. **Fixed WebSocket Resilience** (`src/network/cloud_sync.py`)
- **Application-level heartbeat** every 45 seconds to keep Cloudflare tunnel alive
- **Graceful error handling** for expected Cloudflare disconnects:
  - `WebSocketConnectionClosedException` → INFO log instead of ERROR traceback
  - `WebSocketTimeoutException` → INFO log instead of ERROR traceback
  - `ConnectionResetError` → INFO log instead of ERROR traceback
- **Reconnection tracking** with telemetry counter
- **Clean heartbeat thread shutdown** on disconnect

### 3. **Restart Script** (`restart_fresh.sh`)
```bash
./restart_fresh.sh
```
- Pulls latest code from git
- Restarts systemd service
- Streams logs in real-time

## 🚀 Quick Start

### Installation
```bash
# Navigate to project directory
cd /home/pi/dopamine-hardware

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Enable and start service
sudo systemctl enable $(pwd)/dopamine.service
sudo systemctl start dopamine.service

# View logs
journalctl -u dopamine.service -f
```

### Update and Restart
```bash
# Quick restart with latest code
./restart_fresh.sh
```

## 📦 Module Dependencies

```
src.core.config (no dependencies)
├── src.core.core_logger (no dependencies)
│   └── src.core.telemetry
├── src.hardware.audio (no dependencies)
├── src.hardware.printer
│   ├── src.network.cloud_sync
│   └── src.api.api
├── src.hardware.scanner (depends on hardware.audio)
└── src.ai (no cross-dependencies with hardware)
    ├── src.ai.config (no dependencies)
    ├── src.ai.text (depends on ai.config)
    ├── src.ai.speech (depends on ai.config, ai.text)
    └── src.ai.diagnostics (depends on ai.text)
```

## 🔌 Communication Tiers

1. **Tier 1 (VPC Push)**: Flask server on `0.0.0.0:8080` via Cloudflare Tunnel
2. **Tier 2 (WebSocket)**: Persistent WSS with 45-second heartbeat
3. **Tier 3 (REST Polling)**: Polls `/api/printer/pending` every 15 seconds

## 🛡️ WebSocket Resilience Features

- **Protocol-level keepalive**: `ping_interval=30`, `ping_timeout=10`
- **Application-level heartbeat**: JSON message every 45 seconds
- **Graceful disconnect handling**: Expected Cloudflare drops logged as INFO
- **Automatic reconnection**: 5-second delay between attempts
- **Telemetry tracking**: Reconnection count sent to Worker

## 📝 Import Pattern

All imports now use the `src.` prefix:
```python
# Core
from src.core.config import WORKER_URL, WS_URL
from src.core.core_logger import setup_logger
from src.core.telemetry import telemetry_worker

# Hardware
from src.hardware.printer import print_and_ack
from src.hardware.scanner import scanner_worker
from src.hardware.audio import play_sound

# Network
from src.network.cloud_sync import run_websocket, run_rest_polling

# API
from src.api.api import app

# AI
import src.ai as ai
```

## 🧪 Testing

```bash
# Test import chain
python3 -c "from src.core.config import WORKER_URL; print('OK')"

# Test main entry point
python3 main.py
```

## 🔍 Logs

All logs are:
1. Printed to console (stdout)
2. Written to local SQLite database (`dopamine_logs.db`)
3. Streamed asynchronously to Cloudflare Worker telemetry endpoint

View logs:
```bash
journalctl -u dopamine.service -f
```

## 🔒 Security

- **Input sanitization**: All print jobs sanitized before hardware interaction
- **Log injection prevention**: All logged data sanitized
- **No secrets in code**: Credentials managed via Cloudflare Tunnel
- **USB allowlisting**: Only approved device IDs accepted

## 📚 Documentation

- `ARCHITECTURE.md` - System architecture overview
- `WORKER_AI.md` - Cloudflare AI integration details
- `REFACTORING_SUMMARY.md` - Original refactoring notes
- `AGENTS.md` - AI agent instructions

## 🐛 Troubleshooting

### Service won't start
```bash
sudo journalctl -u dopamine.service -n 50 --no-pager
```

### Import errors
Ensure you're running from the repository root where `src/` directory exists.

### WebSocket keeps disconnecting
This is **expected behavior** on Cloudflare. The new implementation handles this gracefully with automatic reconnection and application-level heartbeats.
