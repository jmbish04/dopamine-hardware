#!/usr/bin/env python3
import evdev
import sys
import time

def find_scanner():
    print("🔍 Searching for USB Barcode Scanner...")
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    
    scanner = None
    # Use the same updated logic as hardware.py to find the Tera scanner
    for name_match in ["tera", "usb adapter", "scanner", "keyboard"]:
        scanner = next((d for d in devices if name_match in d.name.lower() and "logitech" not in d.name.lower()), None)
        if scanner:
            break
            
    return scanner

def main():
    scanner = find_scanner()
    if not scanner:
        print("❌ Barcode scanner not found!")
        print("Make sure it's plugged in and recognized as an input device.")
        sys.exit(1)

    print(f"✅ Found Scanner: {scanner.name} at {scanner.path}")
    print("⚠️  Attempting to grab device...")
    
    try:
        scanner.grab()
        print("✅ Successfully grabbed the scanner!")
    except IOError:
        print("❌ ERROR: Device is busy. It is likely being used by dopamine.service.")
        print("Please stop the service first by running:")
        print("    sudo systemctl stop dopamine.service")
        sys.exit(1)

    print("\nREADY! Scan a barcode now (Press Ctrl+C to exit)...")
    
    keys = {
        evdev.ecodes.KEY_0: '0', evdev.ecodes.KEY_1: '1', evdev.ecodes.KEY_2: '2',
        evdev.ecodes.KEY_3: '3', evdev.ecodes.KEY_4: '4', evdev.ecodes.KEY_5: '5',
        evdev.ecodes.KEY_6: '6', evdev.ecodes.KEY_7: '7', evdev.ecodes.KEY_8: '8',
        evdev.ecodes.KEY_9: '9',
        
        # A-Z support if barcodes contain letters
        evdev.ecodes.KEY_A: 'A', evdev.ecodes.KEY_B: 'B', evdev.ecodes.KEY_C: 'C',
        evdev.ecodes.KEY_D: 'D', evdev.ecodes.KEY_E: 'E', evdev.ecodes.KEY_F: 'F',
        evdev.ecodes.KEY_G: 'G', evdev.ecodes.KEY_H: 'H', evdev.ecodes.KEY_I: 'I',
        evdev.ecodes.KEY_J: 'J', evdev.ecodes.KEY_K: 'K', evdev.ecodes.KEY_L: 'L',
        evdev.ecodes.KEY_M: 'M', evdev.ecodes.KEY_N: 'N', evdev.ecodes.KEY_O: 'O',
        evdev.ecodes.KEY_P: 'P', evdev.ecodes.KEY_Q: 'Q', evdev.ecodes.KEY_R: 'R',
        evdev.ecodes.KEY_S: 'S', evdev.ecodes.KEY_T: 'T', evdev.ecodes.KEY_U: 'U',
        evdev.ecodes.KEY_V: 'V', evdev.ecodes.KEY_W: 'W', evdev.ecodes.KEY_X: 'X',
        evdev.ecodes.KEY_Y: 'Y', evdev.ecodes.KEY_Z: 'Z',
        evdev.ecodes.KEY_MINUS: '-', evdev.ecodes.KEY_EQUAL: '=',
        evdev.ecodes.KEY_SPACE: ' '
    }

    buffer = ""
    try:
        for event in scanner.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                data = evdev.categorize(event)
                if data.keystate == 1:  # Key down
                    if data.scancode == evdev.ecodes.KEY_ENTER:
                        if buffer:
                            print(f"\n📠 [SUCCESS] Scanned Barcode: {buffer}\n")
                            buffer = ""
                            print("Ready for next scan...")
                    elif data.scancode in keys:
                        buffer += keys[data.scancode]
                        # Print in real-time on the same line to show it's reading
                        sys.stdout.write(f"\rCurrent Buffer: {buffer}")
                        sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n\n🛑 Exiting test script...")
    finally:
        try:
            scanner.ungrab()
        except:
            pass

if __name__ == "__main__":
    main()
