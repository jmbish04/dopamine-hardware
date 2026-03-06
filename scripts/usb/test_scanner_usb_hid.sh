source .venv/bin/activate
python -c "import evdev; print('\n'.join([f'{d.path}: {d.name}' for d in [evdev.InputDevice(p) for p in evdev.list_devices()]]))"
