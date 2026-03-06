import os
import sys
import json
import subprocess
import requests

# --- Configuration ---
CLOUDFLARE_API_TOKEN = os.getenv("CF_API_TOKEN")
ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
AI_MODEL = "@cf/openai/gpt-oss-120b"

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
    if not all([CLOUDFLARE_API_TOKEN, ACCOUNT_ID]):
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

    print(f"🧠 Sending hardware state to {AI_MODEL}...")
    
    # Utilizing the new Responses API endpoint specified in the documentation
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1/responses"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "You are a Codex Senior Engineer diagnosing a hardware bridge. Analyze the provided `lsusb` output "
        "against the user's `udev` rules and Python application code. "
        "Identify if the Vendor ID (VID) and Product ID (PID) for the connected thermal printer and barcode scanner "
        "match the hardcoded values in the files. "
        "If they are mismatched, output the exact line modifications required to fix the code and rules. "
        "Keep your response strictly technical, concise, and formatted in Markdown."
    )
    
    # The Responses API accepts the `input` key, which can cleanly ingest an array of messages
    payload = {
        "model": AI_MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<lsusb_output>\n{lsusb_out}\n</lsusb_output>\n\n<udev_rules>\n{rules_content}\n</udev_rules>\n\n<app_code>\n{app_content}\n</app_code>"}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ Cloudflare API Error: {response.status_code} - {response.text}")
        sys.exit(1)
        
    response_data = response.json()
    result_text = ""
    
    # Bulletproof dynamic schema parsing to prevent NoneType AttributeErrors
    if isinstance(response_data, dict):
        # 1. Standard Cloudflare Workers AI format {"result": {"response": "..."}}
        if isinstance(response_data.get("result"), dict) and "response" in response_data["result"]:
            result_text = response_data["result"]["response"]
        # 2. Open-weight flat format {"result": "..."}
        elif isinstance(response_data.get("result"), str):
            result_text = response_data["result"]
        # 3. Standard OpenAI format {"choices": [{"message": {"content": "..."}}]}
        elif "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
            content = response_data["choices"][0].get("message", {}).get("content")
            if content is not None:
                result_text = content
        # 4. Direct response string {"response": "..."}
        elif isinstance(response_data.get("response"), str):
            result_text = response_data["response"]

    # If parsing completely fails, safely dump the raw payload
    if not result_text:
        result_text = f"⚠️ Could not extract AI text. Raw API Payload:\n{json.dumps(response_data, indent=2)}"
        
    print("\n✨ --- AI Hardware Analysis --- ✨\n")
    print(result_text.strip())
    print("\n✨ ---------------------------- ✨\n")

if __name__ == "__main__":
    main()
