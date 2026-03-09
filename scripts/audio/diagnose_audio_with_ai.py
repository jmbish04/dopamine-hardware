#!/usr/bin/env python3
"""
Comprehensive Audio Diagnostic for the Dopamine Hardware Bridge.

Tests the full audio pipeline: ALSA config → sound devices → playback tools →
TTS generation → audio output. Sends all findings to the Cloudflare Worker AI
diagnostician for analysis and remediation recommendations.

Usage:
    python scripts/audio/diagnose_audio_with_ai.py

Requires:
    - CLOUDFLARE_ACCOUNT_ID (or CF_ACCOUNT_ID)
    - CLOUDFLARE_API_TOKEN  (or CF_API_TOKEN)
"""

import math
import os
import struct
import sys
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import requests
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; env vars may already be set

# --- Configuration ---
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID") or os.getenv("CF_ACCOUNT_ID")
API_TOKEN = (
    os.getenv("CLOUDFLARE_AI_GATEWAY_TOKEN")
    or os.getenv("CF_AI_GATEWAY_TOKEN")
    or os.getenv("CLOUDFLARE_API_TOKEN")
    or os.getenv("CF_API_TOKEN")
)
GATEWAY_NAME = os.getenv("CLOUDFLARE_GATEWAY_NAME") or os.getenv("CF_GATEWAY_NAME", "default-gateway")

AI_MODEL = "workers-ai/@cf/openai/gpt-oss-120b"
TTS_MODEL = "@cf/deepgram/aura-2-en"

# The ALSA device the bridge hardcodes in audio.py
APP_ALSA_DEVICE = "plughw:3,0"

# Repository root (this file lives at scripts/audio/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Audio tools the bridge depends on
REQUIRED_TOOLS = ["aplay", "mpg123"]
OPTIONAL_TOOLS = ["sox", "ffmpeg", "amixer", "arecord", "jackd", "pulseaudio", "pactl"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cmd(command, timeout=10):
    """Executes a shell command and returns (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s: {command}", -1
    except Exception as e:
        return "", str(e), -1


def read_file(filepath):
    """Safely reads a file, returning an error string on failure."""
    try:
        with open(filepath, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filepath}: {e}"


# ---------------------------------------------------------------------------
# Diagnostic checks
# ---------------------------------------------------------------------------

def check_sound_cards():
    """List all recognised ALSA sound cards."""
    stdout, stderr, rc = run_cmd("cat /proc/asound/cards 2>/dev/null || echo 'No /proc/asound/cards'")
    return {"proc_asound_cards": stdout or stderr, "exit_code": rc}


def check_aplay_devices():
    """List PCM playback devices visible to ALSA."""
    stdout, stderr, rc = run_cmd("aplay -l 2>&1")
    return {"aplay_devices": stdout or stderr, "exit_code": rc}


def check_amixer():
    """Dump the current ALSA mixer state."""
    stdout, stderr, rc = run_cmd("amixer 2>&1")
    return {"amixer_output": stdout or stderr, "exit_code": rc}


def check_asoundrc():
    """Read ALSA configuration files."""
    home_rc = read_file(os.path.expanduser("~/.asoundrc"))
    etc_rc = read_file("/etc/asound.conf")
    project_rc = read_file(str(REPO_ROOT / ".asoundrc"))
    return {
        "home_asoundrc": home_rc,
        "etc_asound_conf": etc_rc,
        "project_asoundrc": project_rc,
    }


def check_tool_availability():
    """Check which audio CLI tools are installed."""
    results = {}
    for tool in REQUIRED_TOOLS + OPTIONAL_TOOLS:
        path = shutil.which(tool)
        results[tool] = {"installed": path is not None, "path": path or "NOT FOUND"}
    return results


def check_jack_status():
    """Probe JACK server status and related environment."""
    stdout, stderr, rc = run_cmd("jack_lsp 2>&1")
    jack_lsp = stdout or stderr

    stdout2, stderr2, rc2 = run_cmd("pgrep -a jackd 2>&1")
    jack_procs = stdout2 or stderr2

    stdout3, stderr3, rc3 = run_cmd("pgrep -a pulseaudio 2>&1")
    pulse_procs = stdout3 or stderr3

    stdout4, stderr4, rc4 = run_cmd("pgrep -a pipewire 2>&1")
    pipewire_procs = stdout4 or stderr4

    return {
        "jack_lsp": jack_lsp,
        "jackd_processes": jack_procs,
        "pulseaudio_processes": pulse_procs,
        "pipewire_processes": pipewire_procs,
    }


def check_audio_group():
    """Verify the current user belongs to the 'audio' group."""
    stdout, _, _ = run_cmd("id")
    groups_out, _, _ = run_cmd("groups")
    return {
        "id_output": stdout,
        "groups": groups_out,
        "in_audio_group": "audio" in groups_out.split() if groups_out else False,
    }


def test_wav_playback():
    """Generate a tiny WAV file and attempt to play it via aplay."""
    wav_path = os.path.join(tempfile.gettempdir(), "diag_test.wav")
    try:
        sample_rate = 44100
        duration = 0.25  # seconds
        freq = 440.0
        with wave.open(wav_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for i in range(int(sample_rate * duration)):
                val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                wf.writeframesraw(struct.pack("<h", val))

        # Attempt 1: app's hardcoded device
        stdout1, stderr1, rc1 = run_cmd(f"aplay -D {APP_ALSA_DEVICE} -q {wav_path} 2>&1", timeout=10)
        # Attempt 2: default device
        stdout2, stderr2, rc2 = run_cmd(f"aplay -q {wav_path} 2>&1", timeout=10)
        # Attempt 3: try each card
        stdout3, stderr3, rc3 = run_cmd("cat /proc/asound/cards 2>/dev/null")
        card_results = {}
        if rc3 == 0 and stdout3:
            for line in stdout3.splitlines():
                line = line.strip()
                if line and line[0].isdigit():
                    card_num = line.split()[0]
                    s, e, r = run_cmd(f"aplay -D plughw:{card_num},0 -q {wav_path} 2>&1", timeout=10)
                    card_results[f"card_{card_num}"] = {"output": s or e, "exit_code": r}

        return {
            "wav_file": wav_path,
            "plughw_3_0": {"output": stdout1 or stderr1, "exit_code": rc1},
            "default_device": {"output": stdout2 or stderr2, "exit_code": rc2},
            "per_card_results": card_results,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


def test_mpg123_playback():
    """Generate a minimal MP3 (via ffmpeg) and test mpg123."""
    mp3_path = os.path.join(tempfile.gettempdir(), "diag_test.mp3")
    wav_path = os.path.join(tempfile.gettempdir(), "diag_test_src.wav")

    try:
        sample_rate = 44100
        duration = 0.25
        freq = 440.0
        with wave.open(wav_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for i in range(int(sample_rate * duration)):
                val = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
                wf.writeframesraw(struct.pack("<h", val))

        # Convert to MP3 using ffmpeg if available
        mp3_ready = False
        if shutil.which("ffmpeg"):
            _, _, rc = run_cmd(f"ffmpeg -y -i {wav_path} -codec:a libmp3lame -qscale:a 9 {mp3_path} 2>&1")
            mp3_ready = rc == 0

        if not mp3_ready:
            return {
                "skipped": True,
                "reason": "ffmpeg not available to create test MP3",
            }

        # Try mpg123 with different ALSA outputs
        stdout1, stderr1, rc1 = run_cmd(f"mpg123 -q {mp3_path} 2>&1", timeout=10)
        stdout2, stderr2, rc2 = run_cmd(f"mpg123 -q -o alsa -a default {mp3_path} 2>&1", timeout=10)
        stdout3, stderr3, rc3 = run_cmd(f"mpg123 -q -o alsa -a {APP_ALSA_DEVICE} {mp3_path} 2>&1", timeout=10)

        # Also check mpg123 supported output modules
        stdout4, stderr4, _ = run_cmd("mpg123 --list-modules 2>&1")

        return {
            "mp3_file": mp3_path,
            "default_output": {"output": stdout1 or stderr1, "exit_code": rc1},
            "alsa_default": {"output": stdout2 or stderr2, "exit_code": rc2},
            "alsa_plughw_3_0": {"output": stdout3 or stderr3, "exit_code": rc3},
            "mpg123_modules": stdout4 or stderr4,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        for p in (mp3_path, wav_path):
            if os.path.exists(p):
                os.remove(p)


def test_tts_generation():
    """Attempt a Cloudflare Aura-2 TTS call and verify we get audio bytes."""
    if not ACCOUNT_ID or not API_TOKEN:
        return {"skipped": True, "reason": "Missing Cloudflare credentials"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{TTS_MODEL}"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"text": "Audio diagnostic test.", "speaker": "athena"}

    tts_path = os.path.join(tempfile.gettempdir(), "diag_tts_test.mp3")
    try:
        resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
        if resp.status_code == 200:
            with open(tts_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            size = os.path.getsize(tts_path)
            return {
                "status_code": resp.status_code,
                "audio_file": tts_path,
                "file_size_bytes": size,
                "success": size > 0,
            }
        else:
            return {
                "status_code": resp.status_code,
                "error": resp.text[:500],
                "success": False,
            }
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        if os.path.exists(tts_path):
            os.remove(tts_path)


def check_systemd_environment():
    """Report relevant env vars that systemd would pass to the service."""
    stdout, _, _ = run_cmd("systemctl show dopamine.service --property=Environment 2>/dev/null")
    env_vars = {
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "NOT SET"),
        "DISPLAY": os.environ.get("DISPLAY", "NOT SET"),
        "PULSE_SERVER": os.environ.get("PULSE_SERVER", "NOT SET"),
        "DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS", "NOT SET"),
    }
    return {
        "systemd_environment": stdout or "Service not found",
        "relevant_env_vars": env_vars,
    }


def read_audio_module():
    """Return the project's audio.py source for the AI to review."""
    return read_file(str(REPO_ROOT / "audio.py"))


# ---------------------------------------------------------------------------
# AI Diagnosis
# ---------------------------------------------------------------------------

def send_to_ai_diagnostician(diagnostic_report):
    """Send the full diagnostic payload to the Worker AI diagnostician."""
    if not all([ACCOUNT_ID, API_TOKEN]):
        print("❌ Missing required environment variables: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID")
        sys.exit(1)

    print(f"\n🧠 Routing audio diagnostics through AI Gateway ({GATEWAY_NAME}) via Unified API to {AI_MODEL}...")

    BASE_URL = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_NAME}/compat"

    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_TOKEN,
        default_headers={"cf-aig-authorization": f"Bearer {API_TOKEN}"},
    )

    system_prompt = (
        "You are a Codex Senior Engineer diagnosing audio playback failures on a headless Raspberry Pi 4 "
        "running the Dopamine Hardware Bridge. The bridge uses Cloudflare Workers AI Deepgram Aura-2 TTS "
        "to generate MP3 files and plays them via `mpg123` (MP3) or `aplay` (WAV). "
        "The user sees JACK server errors when mpg123 tries to play audio. "
        "Analyze ALL diagnostic data provided (ALSA cards, device lists, .asoundrc config, tool versions, "
        "JACK/PulseAudio/PipeWire status, playback test results, systemd environment, and audio.py source code). "
        "You MUST return your response as a valid JSON object strictly containing these keys:\n"
        "  'root_cause'        (string - the primary reason audio playback fails),\n"
        "  'analysis'          (string - detailed breakdown of every finding),\n"
        "  'fix_commands'      (array of strings - exact shell commands to run, in order, to fix the issue),\n"
        "  'code_changes'      (string - markdown diff of changes needed in audio.py, or empty if none),\n"
        "  'severity'          (string - 'critical', 'high', 'medium', or 'low'),\n"
        "  'additional_notes'  (string - anything else the operator should know)."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"<audio_diagnostic_report>\n{json.dumps(diagnostic_report, indent=2)}\n</audio_diagnostic_report>",
        },
    ]

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=4096,
        )

        message_obj = response.choices[0].message
        content = message_obj.content

        if hasattr(message_obj, "reasoning_content") and message_obj.reasoning_content:
            print(f"\n🤔 AI Internal Reasoning:\n{message_obj.reasoning_content.strip()}\n")

        if not content:
            print("⚠️ API returned an empty content block. Raw SDK Response:")
            print(response.model_dump_json(indent=2))
            sys.exit(1)

        structured = json.loads(content)

        print("\n✨ --- AI Audio Diagnosis --- ✨\n")
        print(f"🔴 Root Cause: {structured.get('root_cause', 'N/A')}\n")
        print(f"📋 Analysis:\n{structured.get('analysis', 'N/A')}\n")

        severity = structured.get("severity", "unknown")
        severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
        print(f"{severity_icon} Severity: {severity}\n")

        fix_cmds = structured.get("fix_commands", [])
        if fix_cmds:
            print("🔧 Fix Commands (run in order):")
            for i, cmd in enumerate(fix_cmds, 1):
                print(f"   {i}. {cmd}")

        code_changes = structured.get("code_changes", "")
        if code_changes:
            print(f"\n📝 Code Changes Required:\n{code_changes}")

        notes = structured.get("additional_notes", "")
        if notes:
            print(f"\n💡 Additional Notes:\n{notes}")

        print("\n✨ ----------------------------- ✨\n")
        return structured

    except Exception as e:
        print(f"❌ Error communicating with AI Gateway: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("🔊 DOPAMINE AUDIO DIAGNOSTIC")
    print("=" * 70)

    report = {}

    # 1. Sound cards
    print("\n[1/9] Checking ALSA sound cards...")
    report["sound_cards"] = check_sound_cards()
    print(f"   → {report['sound_cards']['proc_asound_cards'][:120]}")

    # 2. Playback devices
    print("\n[2/9] Listing ALSA playback devices...")
    report["playback_devices"] = check_aplay_devices()
    print(f"   → {report['playback_devices']['aplay_devices'][:120]}")

    # 3. Mixer state
    print("\n[3/9] Reading ALSA mixer state...")
    report["mixer"] = check_amixer()
    print(f"   → {report['mixer']['amixer_output'][:120]}")

    # 4. ALSA config files
    print("\n[4/9] Reading .asoundrc / asound.conf...")
    report["alsa_config"] = check_asoundrc()
    for key, val in report["alsa_config"].items():
        status = "found" if "Error reading" not in val else "missing"
        print(f"   → {key}: {status}")

    # 5. Tool availability
    print("\n[5/9] Checking audio tool availability...")
    report["tools"] = check_tool_availability()
    for tool, info in report["tools"].items():
        icon = "✓" if info["installed"] else "✗"
        print(f"   {icon} {tool}: {info['path']}")

    # 6. JACK / PulseAudio / PipeWire status
    print("\n[6/9] Checking audio server status (JACK/Pulse/PipeWire)...")
    report["audio_servers"] = check_jack_status()

    # 7. User / group
    print("\n[7/9] Checking user audio permissions...")
    report["user_permissions"] = check_audio_group()
    in_group = report["user_permissions"]["in_audio_group"]
    print(f"   → In audio group: {in_group}")

    # 8. WAV playback test
    print("\n[8/9] Testing WAV playback (aplay)...")
    report["wav_playback_test"] = test_wav_playback()
    if "error" not in report["wav_playback_test"]:
        for key in ("plughw_3_0", "default_device"):
            rc = report["wav_playback_test"].get(key, {}).get("exit_code", -1)
            icon = "✓" if rc == 0 else "✗"
            print(f"   {icon} {key}: exit_code={rc}")
    else:
        print(f"   ✗ Error: {report['wav_playback_test']['error']}")

    # 9. MP3 playback test (mpg123)
    print("\n[9/9] Testing MP3 playback (mpg123)...")
    report["mp3_playback_test"] = test_mpg123_playback()
    if report["mp3_playback_test"].get("skipped"):
        print(f"   ⚠ Skipped: {report['mp3_playback_test']['reason']}")
    elif "error" not in report["mp3_playback_test"]:
        for key in ("default_output", "alsa_default", "alsa_plughw_3_0"):
            rc = report["mp3_playback_test"].get(key, {}).get("exit_code", -1)
            icon = "✓" if rc == 0 else "✗"
            print(f"   {icon} {key}: exit_code={rc}")
    else:
        print(f"   ✗ Error: {report['mp3_playback_test']['error']}")

    # Bonus checks
    print("\n[+] Testing TTS generation (Cloudflare Aura-2)...")
    report["tts_generation"] = test_tts_generation()
    if report["tts_generation"].get("success"):
        print(f"   ✓ TTS OK ({report['tts_generation']['file_size_bytes']} bytes)")
    elif report["tts_generation"].get("skipped"):
        print(f"   ⚠ Skipped: {report['tts_generation']['reason']}")
    else:
        print(f"   ✗ TTS failed: {report['tts_generation'].get('error', 'unknown')}")

    print("\n[+] Checking systemd environment...")
    report["systemd_env"] = check_systemd_environment()

    print("\n[+] Reading audio.py source...")
    report["audio_py_source"] = read_audio_module()

    # --- Send to AI ---
    print("\n" + "=" * 70)
    send_to_ai_diagnostician(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
