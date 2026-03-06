import os
import sys
import json
import subprocess
from openai import OpenAI

# --- Configuration ---
ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
# Uses your existing CF_API_TOKEN as the Gateway authentication token
API_TOKEN = os.getenv("CF_AI_GATEWAY_TOKEN") or os.getenv("CF_API_TOKEN") 
GATEWAY_NAME = os.getenv("CF_GATEWAY_NAME", "default-gateway")

# Universal Routing: Prefix the standard Cloudflare model tag with 'workers-ai/'
AI_MODEL = "workers-ai/@cf/openai/gpt-oss-120b"

def run_cmd(command):
    """Executes a shell command safely."""
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {command}\nError: {e.stderr.strip()}")
        sys.exit(1)

def read_file(filepath):
    """Safely reads a file's contents, returning an error string if missing or restricted."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filepath}: {e}"

def main():
    if not all([ACCOUNT_ID, API_TOKEN]):
        print("❌ Missing required environment variables: CF_API_TOKEN, CF_ACCOUNT_ID")
        sys.exit(1)

    print("🔍 Scanning USB bus...")
    lsusb_out = run_cmd("lsusb")
    
    print("📄 Reading configuration files...")
    rules_content = read_file("/etc/udev/rules.d/99-epson-printer.rules")
    if "Error reading" in rules_content:
        rules_content = read_file("/etc/udev/rules.d/99-escpos.rules")
        
    app_content = read_file("app.py")
    if "Error reading" in app_content:
        app_content = read_file("hardware.py")

    print(f"🧠 Routing hardware state through AI Gateway ({GATEWAY_NAME}) via Universal Routing to {AI_MODEL}...")
    
    # Point the SDK at the generic /openai Gateway endpoint
    # The SDK will automatically append /chat/completions to this cleanly
    BASE_URL = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_NAME}/openai"
    
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_TOKEN,
    )
    
    # Strict JSON Schema defining exactly what the model is allowed to return
    response_schema = {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": "A concise explanation of the hardware state and if VIDs/PIDs match."
            },
            "mismatch_found": {
                "type": "boolean",
                "description": "True if lsusb output contradicts the rules or python code."
            },
            "required_modifications": {
                "type": "string",
                "description": "Markdown diff of the exact line changes needed. Empty if no mismatch."
            }
        },
        "required": ["analysis", "mismatch_found", "required_modifications"],
        "additionalProperties": False,
    }
    
    system_prompt = (
        "You are a Codex Senior Engineer diagnosing a hardware bridge. Analyze the provided `lsusb` output "
        "against the user's `udev` rules and Python application code. "
        "Identify if the Vendor ID (VID) and Product ID (PID) for the connected thermal printer and barcode scanner "
        "match the hardcoded values in the files. "
        "Return a structured JSON object matching the provided schema."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"<lsusb_output>\n{lsusb_out}\n</lsusb_output>\n\n<udev_rules>\n{rules_content}\n</udev_rules>\n\n<app_code>\n{app_content}\n</app_code>"}
    ]
    
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {"name": "hardware_diagnostic", "schema": response_schema, "strict": True}},
            temperature=0.2,
        )
        
        # The OpenAI SDK handles the payload extraction natively
        structured_json = json.loads(response.choices[0].message.content)
        
        print("\n✨ --- AI Hardware Analysis --- ✨\n")
        print(f"Diagnosis: {structured_json.get('analysis')}\n")
        
        if structured_json.get('mismatch_found'):
            print("🚨 MISMATCH DETECTED. Apply the following fixes:\n")
            print(structured_json.get('required_modifications'))
        else:
            print("✅ Hardware configuration is perfectly aligned. No changes needed.")
            
        print("\n✨ ---------------------------- ✨\n")

    except Exception as e:
        print(f"❌ Error communicating with AI Gateway: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
