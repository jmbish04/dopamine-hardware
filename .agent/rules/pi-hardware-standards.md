# Rule: Python Edge Hardware Standards

- **Virtual Environment:** Always assume the execution context is `/home/pi/dopamine-hardware/.venv/bin/python`. When suggesting bash commands, prepend them with `source .venv/bin/activate`.
- **Dependency Management:** If a new library is added to the codebase, immediately append it to `requirements.txt`.
- **USB Interactions:** - Utilize `python-escpos` for all printing. 
  - Ensure the `profile="TM-T20III"` argument is passed to the `Usb()` constructor.
  - QR Codes must ALWAYS be generated using the `native=True` parameter to utilize the printer's hardware renderer for maximum contrast and scannability.
- **Logging:** Use the root `logging` module. Do not use print statements. The `DualLoggerHandler` automatically routes `logging.info` and `logging.error` to both the local SQLite DB and the Cloudflare Worker telemetry API.
- **API Fetching:** Always include a `timeout=` parameter on the `requests` module (e.g., `timeout=5`). Never allow a network call to hang indefinitely.
- **Systemd Reloading:** Whenever suggesting changes to `app.py`, remind the user to run `sudo systemctl restart dopamine.service`.
