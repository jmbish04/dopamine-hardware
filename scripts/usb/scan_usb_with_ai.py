import os
import sys
import json
import subprocess
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
# Uses your existing CLOUDFLARE_API_TOKEN as the Gateway authentication token
API_TOKEN = os.getenv("CLOUDFLARE_AI_GATEWAY_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN")
GATEWAY_NAME = os.getenv("CLOUDFLARE_GATEWAY_NAME", "default-gateway")

# FIX 1: Use a valid Cloudflare Workers AI model tag.
# "gpt-oss-120b" does not exist. We use Llama 3.1 8B Instruct here as a reliable default.
AI_MODEL = "worker-ai/@cf/openai/gpt-oss-120b"

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
        print("❌ Missing required environment variables: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID")
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

    print(f"🧠 Routing hardware state through AI Gateway ({GATEWAY_NAME}) via Unified API to {AI_MODEL}...")
    
    # The SDK automatically appends /chat/completions, constructing your exact curl URL
    BASE_URL = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_NAME}/compat"
    
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_TOKEN, # Satisfies the SDK's internal validation
        default_headers={
            "cf-aig-authorization": f"Bearer {API_TOKEN}" # Explicit Gateway Auth
        }
    )
    
    system_prompt = (
        "You are a Codex Senior Engineer diagnosing a hardware bridge. Analyze the provided `lsusb` output "
        "against the user's `udev` rules and Python application code. "
        "Identify if the Vendor ID (VID) and Product ID (PID) for the connected thermal printer and barcode scanner "
        "match the hardcoded values in the files. "
        "You MUST return your response as a valid JSON object strictly containing three keys: "
        "'analysis' (string explaining the state), 'mismatch_found' (boolean true/false), and 'required_modifications' "
        "(string containing markdown diffs, or empty if no mismatch)."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"<lsusb_output>\n{lsusb_out}\n</lsusb_output>\n\n<udev_rules>\n{rules_content}\n</udev_rules>\n\n<app_code>\n{app_content}\n</app_code>"}
    ]
    
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        
        content = response.choices[0].message.content
        
        if not content:
            print("⚠️ API returned an empty content block. Raw SDK Response:")
            print(response.model_dump_json(indent=2))
            sys.exit(1)
            
        structured_json = json.loads(content)
        
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
