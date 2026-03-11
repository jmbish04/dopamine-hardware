# Migration Guide: v1 → v2 (Modular Structure)

## Overview

Version 2.0 introduces a complete modular restructure with all source code organized into the `src/` directory. This guide will help you migrate from the old flat structure to the new modular architecture.

## What Changed?

### File Structure
```
OLD (v1):                          NEW (v2):
├── config.py                      ├── src/
├── core_logger.py                 │   ├── core/
├── telemetry.py                   │   │   ├── config.py
├── audio.py                       │   │   ├── core_logger.py
├── printer.py                     │   │   └── telemetry.py
├── scanner.py                     │   ├── hardware/
├── cloud_sync.py                  │   │   ├── audio.py
├── api.py                         │   │   ├── printer.py
├── app.py                         │   │   └── scanner.py
├── ai/                            │   ├── network/
│   ├── config.py                  │   │   └── cloud_sync.py
│   ├── text.py                    │   ├── api/
│   ├── speech.py                  │   │   ├── api.py
│   └── diagnostics.py             │   │   └── app.py
└── main.py                        │   └── ai/
                                   │       ├── config.py
                                   │       ├── text.py
                                   │       ├── speech.py
                                   │       └── diagnostics.py
                                   ├── main.py (updated)
                                   └── restart_fresh.sh (new)
```

### Import Changes

**Before (v1):**
```python
from config import WORKER_URL
from core_logger import setup_logger
from telemetry import telemetry_worker
from printer import print_and_ack
from scanner import scanner_worker
from cloud_sync import run_websocket
from api import app
import ai
```

**After (v2):**
```python
from src.core.config import WORKER_URL
from src.core.core_logger import setup_logger
from src.core.telemetry import telemetry_worker
from src.hardware.printer import print_and_ack
from src.hardware.scanner import scanner_worker
from src.network.cloud_sync import run_websocket
from src.api.api import app
import src.ai as ai
```

## Critical WebSocket Improvements (cloud_sync.py)

### v1 Issues
- Noisy error logs every 5-9 minutes with full tracebacks
- No application-level heartbeat
- Poor handling of expected Cloudflare disconnects

### v2 Fixes
1. **Application-level heartbeat** every 45 seconds
2. **Graceful error handling** for expected disconnects:
   - `WebSocketConnectionClosedException` → INFO log
   - `WebSocketTimeoutException` → INFO log
   - `ConnectionResetError` → INFO log
3. **Reconnection tracking** with counter sent to telemetry
4. **Clean thread shutdown** for heartbeat thread

## Migration Steps

### For Development/Testing

1. **Pull latest code:**
   ```bash
   cd /home/pi/dopamine-hardware
   git pull
   ```

2. **Test imports:**
   ```bash
   python3 -c "from src.core.config import WORKER_URL; print('✅ Imports working')"
   ```

3. **Run application:**
   ```bash
   python3 main.py
   ```

### For Production (Raspberry Pi)

1. **Pull latest code:**
   ```bash
   cd /home/pi/dopamine-hardware
   git pull
   ```

2. **No service changes required** - `dopamine.service` still points to `main.py`

3. **Restart service:**
   ```bash
   sudo systemctl restart dopamine.service
   ```

4. **Or use the new convenience script:**
   ```bash
   ./restart_fresh.sh
   ```

### Using restart_fresh.sh

The new `restart_fresh.sh` script automates the update process:

```bash
./restart_fresh.sh
```

This script will:
1. Pull latest code from git
2. Restart the systemd service
3. Stream logs in real-time

## Backwards Compatibility

- **Old files preserved**: Original files remain in the root directory for reference
- **No service config changes**: `dopamine.service` unchanged
- **Same entry point**: `main.py` is still the entry point
- **Same functionality**: All features work exactly the same

## Testing Checklist

After migration, verify:

- [ ] Service starts without errors
- [ ] WebSocket connects and stays connected
- [ ] Printer receives and processes jobs
- [ ] Scanner detects barcodes
- [ ] Logs are written to SQLite database
- [ ] Logs are sent to Cloudflare Worker
- [ ] Audio feedback plays on events
- [ ] WebSocket reconnects gracefully after disconnect
- [ ] Heartbeat messages sent every 45 seconds (check logs)

## Monitoring WebSocket Health

### Check logs for heartbeat activity:
```bash
journalctl -u dopamine.service -f | grep -i heartbeat
```

Expected output:
```
💓 [WS] Heartbeat sent
💓 [WS] Heartbeat acknowledged
```

### Check reconnection count:
```bash
journalctl -u dopamine.service | grep -i "reconnect"
```

Expected behavior:
- Reconnections every 5-9 minutes are **normal** on Cloudflare
- Logs should be INFO level, not ERROR

## Troubleshooting

### Import errors
```
ModuleNotFoundError: No module named 'src'
```
**Solution**: Ensure you're running from the repository root where `src/` directory exists.

### Service won't start
```bash
sudo journalctl -u dopamine.service -n 50 --no-pager
```

### Old imports still being used
**Solution**: Ensure `main.py` has been updated with the new code. Run `git pull` again.

### WebSocket keeps disconnecting
This is **expected behavior** on Cloudflare. The new v2 code handles this gracefully with:
- Application-level heartbeats
- INFO-level logging (not ERROR)
- Automatic reconnection

## Rollback (Emergency Only)

If you need to rollback to v1:

1. **Checkout previous commit:**
   ```bash
   git log --oneline -n 5  # Find the commit before migration
   git checkout <commit-hash>
   ```

2. **Restart service:**
   ```bash
   sudo systemctl restart dopamine.service
   ```

## Questions?

See:
- `MODULAR_STRUCTURE.md` - New structure overview
- `ARCHITECTURE.md` - Updated architecture documentation
- `WORKER_AI.md` - AI integration details

## Summary

✅ **What You Get:**
- Cleaner, more maintainable code structure
- Better WebSocket resilience
- Less noisy logs
- Application-level heartbeats
- Reconnection tracking

✅ **What Stays the Same:**
- All functionality
- Service configuration
- Entry point (main.py)
- Deployment process

🎯 **Key Command:**
```bash
./restart_fresh.sh
```
