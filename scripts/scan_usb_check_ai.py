import os
import sys
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
    # Attempt to read the rules file (handling potential naming variations)
    rules_content = read_file("/etc/udev/rules.d/99-epson-printer.rules")
    if "Error reading" in rules_content:
        rules_content = read_file("/etc/udev/rules.d/99-escpos.rules")
        
    # Attempt to read the monolithic app.py or fallback to modularized hardware.py
    app_content = read_file("app.py")
    if "Error reading" in app_content:
        app_content = read_file("hardware.py")

    print(f"🧠 Sending hardware state to {AI_MODEL}...")
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{AI_MODEL}"
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
    
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<lsusb_output>\n{lsusb_out}\n</lsusb_output>\n\n<udev_rules>\n{rules_content}\n</udev_rules>\n\n<app_code>\n{app_content}\n</app_code>"}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ Cloudflare API Error: {response.status_code} - {response.text}")
        sys.exit(1)
        
    result_text = response.json().get("result", {}).get("response", "").strip()
    
    print("\n✨ --- AI Hardware Analysis --- ✨\n")
    print(result_text)
    print("\n✨ ---------------------------- ✨\n")

if __name__ == "__main__":
    main()
