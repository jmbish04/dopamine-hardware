#!/usr/bin/env python3
"""
Test script for the worker_ai module.
Demonstrates all available functions with practical examples.
"""

import os
import sys
import logging

# Add parent directory to path to import worker_ai
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker_ai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_generate_text():
    """Test basic text generation."""
    print("\n" + "="*70)
    print("TEST 1: Text Generation")
    print("="*70)

    result = worker_ai.generate_text(
        prompt="What is edge computing? Answer in one sentence.",
        max_tokens=100,
        temperature=0.7
    )

    if result:
        print(f"✓ Success! Generated text:\n{result}")
        return True
    else:
        print("✗ Failed to generate text")
        return False


def test_generate_structured_response():
    """Test structured JSON response generation."""
    print("\n" + "="*70)
    print("TEST 2: Structured Response Generation")
    print("="*70)

    schema = {
        "task_name": "string - name of the task",
        "priority": "string - high/medium/low",
        "estimated_minutes": "number - estimated time to complete",
        "tags": "array of strings - relevant tags"
    }

    result = worker_ai.generate_structured_response(
        prompt="Create a task for writing documentation for a hardware API. Include priority, time estimate, and tags.",
        json_schema=schema,
        temperature=0.3
    )

    if result:
        print("✓ Success! Generated structured response:")
        print(json.dumps(result, indent=2))
        return True
    else:
        print("✗ Failed to generate structured response")
        return False


def test_generate_voice():
    """Test text-to-speech generation."""
    print("\n" + "="*70)
    print("TEST 3: Text-to-Speech (TTS)")
    print("="*70)

    text = "The dopamine hardware bridge is operational and ready for tasks."
    output_path = "/tmp/test_tts_output.mp3"

    result = worker_ai.generate_voice(
        text=text,
        output_path=output_path,
        speaker="luna"
    )

    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"✓ Success! Audio saved to: {result}")
        print(f"  File size: {file_size} bytes")
        return True
    else:
        print("✗ Failed to generate audio")
        return False


def test_task_completion_audio_completed():
    """Test task completion audio for completed tasks."""
    print("\n" + "="*70)
    print("TEST 4: Task Completion Audio (Completed)")
    print("="*70)

    result = worker_ai.generate_task_completion_audio(
        task_name="Write API Documentation",
        action="completed",
        minutes_spent=45,
        other_tasks=["Review Pull Request", "Update Tests", "Deploy to Production"],
        recommended_next="Review Pull Request",
        output_path="/tmp/task_completed.mp3",
        speaker="luna"
    )

    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"✓ Success! Task completion audio saved to: {result}")
        print(f"  File size: {file_size} bytes")
        print(f"  Reminder: Play 'done.wav' sound effect before this audio")
        return True
    else:
        print("✗ Failed to generate task completion audio")
        return False


def test_task_completion_audio_paused():
    """Test task completion audio for paused tasks."""
    print("\n" + "="*70)
    print("TEST 5: Task Completion Audio (Paused)")
    print("="*70)

    result = worker_ai.generate_task_completion_audio(
        task_name="Database Migration",
        action="paused",
        minutes_spent=30,
        output_path="/tmp/task_paused.mp3",
        speaker="hermes"
    )

    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"✓ Success! Task paused audio saved to: {result}")
        print(f"  File size: {file_size} bytes")
        print(f"  Reminder: Play 'paused.wav' sound effect before this audio")
        return True
    else:
        print("✗ Failed to generate task paused audio")
        return False


def test_diagnose_hardware():
    """Test hardware diagnostics (requires actual hardware data)."""
    print("\n" + "="*70)
    print("TEST 6: Hardware Diagnostics (Mock)")
    print("="*70)

    # Mock data for testing
    lsusb_output = """
Bus 001 Device 002: ID 04b8:0e28 Seiko Epson Corp. TM-T20III Receipt Printer
Bus 001 Device 003: ID 05fe:1010 Chesen Electronics Corp. Tera Barcode Scanner
"""

    udev_rules = """
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", ATTRS{idProduct}=="0e28", MODE="0666"
"""

    app_code = """
VENDOR_ID = 0x04b8
PRODUCT_ID = 0x0e28
"""

    result = worker_ai.diagnose_hardware(
        lsusb_output=lsusb_output,
        udev_rules=udev_rules,
        app_code=app_code
    )

    if result:
        print("✓ Success! Hardware diagnostic results:")
        print(json.dumps(result, indent=2))
        return True
    else:
        print("✗ Failed to run hardware diagnostics")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("WORKER_AI MODULE TEST SUITE")
    print("="*70)

    # Check for required environment variables
    required_vars = ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]
    alt_vars = ["CF_ACCOUNT_ID", "CF_API_TOKEN"]

    has_creds = False
    if all(os.environ.get(var) for var in required_vars):
        has_creds = True
    elif all(os.environ.get(var) for var in alt_vars):
        has_creds = True

    if not has_creds:
        print("\n⚠️  WARNING: Cloudflare credentials not found in environment.")
        print("Set either:")
        print("  - CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
        print("  - CF_ACCOUNT_ID and CF_API_TOKEN")
        print("\nTests will fail without proper credentials.\n")

    # Run tests
    tests = [
        ("Text Generation", test_generate_text),
        ("Structured Response", test_generate_structured_response),
        ("Text-to-Speech", test_generate_voice),
        ("Task Completion (Completed)", test_task_completion_audio_completed),
        ("Task Completion (Paused)", test_task_completion_audio_paused),
        ("Hardware Diagnostics", test_diagnose_hardware)
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n✗ Test '{test_name}' raised exception: {e}")
            results[test_name] = False

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*70 + "\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
