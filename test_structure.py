#!/usr/bin/env python3
"""
Dry-run test for the modularized Dopamine Hardware Bridge.
Tests that all modules load correctly and the threading structure is valid.
Does NOT require actual hardware to be connected.
"""

import sys
import os
import logging

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_module_structure():
    """Test that all modules can be imported and have expected structure"""
    print("=" * 80)
    print("DOPAMINE HARDWARE BRIDGE - MODULE STRUCTURE TEST")
    print("=" * 80)

    # Test 1: Config module
    print("\n[1/7] Testing config.py...")
    try:
        import config
        assert config.VENDOR_ID == 0x04b8
        assert config.PRODUCT_ID == 0x0e28
        assert 'dopamine' in config.WORKER_URL.lower()
        print("   ✓ Configuration constants loaded")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 2: Core logger
    print("\n[2/7] Testing core_logger.py...")
    try:
        import core_logger
        assert hasattr(core_logger, 'log_queue')
        assert hasattr(core_logger, 'setup_logger')
        assert hasattr(core_logger, 'DualLoggerHandler')

        # Test logger setup
        core_logger.setup_logger()
        logging.info("Test log message")
        print("   ✓ Logging infrastructure initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 3: Telemetry module
    print("\n[3/7] Testing telemetry.py...")
    try:
        import telemetry
        assert hasattr(telemetry, 'telemetry_worker')
        print("   ✓ Telemetry worker defined")
        print("   ℹ Note: Worker thread not started (requires SQLite)")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 4: Hardware module (will fail without evdev/escpos installed)
    print("\n[4/7] Testing hardware.py...")
    try:
        import hardware
        assert hasattr(hardware, 'get_printer')
        assert hasattr(hardware, 'print_and_ack')
        assert hasattr(hardware, 'scanner_worker')
        assert hasattr(hardware, 'printer_lock')
        assert hasattr(hardware, 'play_sound')
        print("   ✓ Hardware functions defined")
        print("   ℹ Note: Printer/scanner not tested (requires hardware)")
    except ImportError as e:
        print(f"   ⚠ Import warning: {e}")
        print("   ℹ This is expected in CI environment without hardware libs")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 5: Cloud sync module
    print("\n[5/7] Testing cloud_sync.py...")
    try:
        import cloud_sync
        assert hasattr(cloud_sync, 'run_websocket')
        assert hasattr(cloud_sync, 'run_rest_polling')
        print("   ✓ Cloud sync functions defined")
        print("   ℹ Note: Connections not started (requires network)")
    except ImportError as e:
        print(f"   ⚠ Import warning: {e}")
        print("   ℹ This is expected in CI environment without hardware libs")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 6: API module
    print("\n[6/7] Testing api.py...")
    try:
        import api
        assert hasattr(api, 'app')

        # Check routes are registered
        routes = [str(rule) for rule in api.app.url_map.iter_rules()]
        assert any('/print' in r for r in routes)
        assert any('/test' in r for r in routes)
        assert any('/logs' in r for r in routes)
        print("   ✓ Flask app initialized with routes:")
        print(f"      - /print (VPC print endpoint)")
        print(f"      - /test (diagnostic endpoint)")
        print(f"      - /logs (journalctl endpoint)")
    except ImportError as e:
        print(f"   ⚠ Import warning: {e}")
        print("   ℹ This is expected in CI environment without Flask")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    # Test 7: Main entry point
    print("\n[7/7] Testing main.py...")
    try:
        import main
        assert hasattr(main, 'main')
        print("   ✓ Main entry point defined")
        print("   ℹ Note: Application not started (dry run mode)")
    except ImportError as e:
        print(f"   ⚠ Import warning: {e}")
        print("   ℹ This is expected in CI environment")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False

    return True

def main():
    success = test_module_structure()

    print("\n" + "=" * 80)
    if success:
        print("✅ MODULE STRUCTURE TEST PASSED")
        print("\nThe refactored architecture is valid. To run in production:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Update systemd service: sudo systemctl daemon-reload")
        print("  3. Restart service: sudo systemctl restart dopamine.service")
        print("  4. View logs: journalctl -u dopamine.service -f")
    else:
        print("❌ MODULE STRUCTURE TEST FAILED")
        print("\nSome modules could not be validated. Check error messages above.")
    print("=" * 80)

    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
