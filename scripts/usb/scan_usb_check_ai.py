import os
import sys
import json
import subprocess
import requests

# ---------------------------------------------------------------------
# Configuration – read from environment (set via `wrangler secret put`)
# ---------------------------------------------------------------------
ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
GATEWAY_NAME = os.getenv("CF_GATEWAY_NAME", "default-gateway")
# The token must be bound as AI_GATEWAY_TOKEN; we fall back to CF_API_TOKEN for local testing.
API_TOKEN = os.getenv("CF_AI_GATEWAY_TOKEN") or os.getenv("CF_API_TOKEN")
AI_MODEL = "gpt-oss-120b"

if not all([ACCOUNT_ID, API_TOKEN]):
    print("❌ Missing required environment variables: CF_ACCOUNT_ID and AI_GATEWAY_TOKEN (or CF_API_TOKEN)")
    sys.exit(1)

print(f"API TOKEN: {API_TOKEN}")

# ---------------------------------------------------------------------
# Helper functions (unchanged from your original script)
# ---------------------------------------------------------------------
def run_cmd(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {command}\nError: {e.stderr.strip()}")
        sys.exit(1)

def read_file(filepath: str) -> str:
    try:
        with open(filepath, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filepath}: {e}"

# ---------------------------------------------------------------------
# Build the **correct** base URL for the OpenAI‑compatible gateway
# ---------------------------------------------------------------------
# NOTE: we stop at the provider name – the gateway expects the path
#       /chat/completions directly after the provider.
BASE_URL = (
    f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_NAME}/workers-ai"
)
CHAT_ENDPOINT = f"{BASE_URL}/chat/completions"

# ---------------------------------------------------------------------
# Structured response schema (unchanged)
# ---------------------------------------------------------------------
response_schema = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string", "description": "A concise explanation of the hardware state and if VIDs/PIDs match."},
        "mismatch_found": {"type": "boolean", "description": "True if lsusb output contradicts the rules or python code."},
        "required_modifications": {"type": "string", "description": "Markdown diff of the exact line changes needed. Empty if no mismatch."}
    },
    "required": ["analysis", "mismatch_found", "required_modifications"],
    "additionalProperties": False,
}

system_prompt = (
    "You are a Codex Senior Engineer diagnosing a hardware bridge. Analyze the provided `lsusb` output "
    "against the user's `udev` rules and Python application code. Identify if the Vendor ID (VID) and "
    "Product ID (PID) for the connected thermal printer and barcode scanner match the hardcoded values in "
    "the files. Return a structured JSON object matching the provided schema."
)

# ---------------------------------------------------------------------
# Gather inputs (unchanged)
# ---------------------------------------------------------------------
print("🔍 Scanning USB bus…")
lsusb_out = run_cmd("lsusb")

print("📄 Reading configuration files…")
rules_content = read_file("/etc/udev/rules.d/99-epson-printer.rules")
if "Error reading" in rules_content:
    rules_content = read_file("/etc/udev/rules.d/99-escpos.rules")

app_content = read_file("app.py")
if "Error reading" in app_content:
    app_content = read_file("hardware.py")

print(f"🧠 Routing hardware state through AI Gateway ({GATEWAY_NAME}) to {AI_MODEL}…")

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": f"<lsusb_output>\n{lsusb_out}\n</lsusb_output>\n\n<udev_rules>\n{rules_content}\n</udev_rules>\n\n<app_code>\n{app_content}\n</app_code>"}
]

payload = {
    "model": AI_MODEL,
    "messages": messages,
    "response_format": {
        "type": "json_schema",
        "json_schema": {"name": "hardware_diagnostic", "schema": response_schema}
    },
    "temperature": 0.2,
}

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}

try:
    resp = requests.post(CHAT_ENDPOINT, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # The response payload from the gateway follows the OpenAI schema
    content = data["choices"][0]["message"]["content"]
    structured_json = json.loads(content)

    print("\n✨ --- AI Hardware Analysis --- ✨\n")
    print(f"Diagnosis: {structured_json.get('analysis')}\n")
    if structured_json.get('mismatch_found'):
        print("🚨 MISMATCH DETECTED. Apply the following fixes:\n")
        print(structured_json.get('required_modifications'))
    else:
        print("✅ Hardware configuration is perfectly aligned. No changes needed.")
    print("\n✨ ---------------------------- ✨\n")
except requests.HTTPError as http_err:
    print(f"❌ HTTP error: {http_err.response.status_code} – {http_err.response.text}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
