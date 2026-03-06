# Workflow: Update and Test Hardware Bridge

## Objective
Safely implement code changes to the Raspberry Pi hardware bridge, deploy them via the GitOps pipeline, and verify hardware functionality.

## Execution Steps
1. **Code Modification:**
   - Update `app.py` or auxiliary scripts. 
   - Ensure thread locks (`printer_lock`) are respected if modifying USB interactions.
2. **Dependency Check:**
   - If new imports are used, verify they exist in `requirements.txt`.
3. **Commit & Push:**
   - Commit changes to the `main` branch and push to GitHub.
   - *Note: The Raspberry Pi's cron job (`autoupdate.sh`) checks for updates every minute. It will automatically pull changes, install new pip requirements, and restart the `dopamine.service`.*
4. **Verification via Diagnostics:**
   - Execute the diagnostic script to force a local hardware test and telemetry push:
     ```bash
     source .venv/bin/activate
     python run_diagnostics.py
     ```
   - Verify the physical printer outputs the "DIAGNOSTIC TEST" receipt.
   - Check the Cloudflare Worker D1 `system_logs` table to ensure the telemetry was successfully received.
5. **Daemon Log Check:**
   - If the printer fails, inspect the systemd logs to diagnose USB or network errors:
     ```bash
     sudo journalctl -u dopamine.service -n 50 --no-pager
     ```
