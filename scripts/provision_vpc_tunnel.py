# scripts/provision_vpc_tunnel.py
import os
import sys
import json
import subprocess
import requests

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------
CLOUDFLARE_API_TOKEN = os.getenv("CF_API_TOKEN")
ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
TUNNEL_NAME = "dopamine-printer-tunnel"

if not CLOUDFLARE_API_TOKEN or not ACCOUNT_ID:
    print("[ERROR] Please export CF_API_TOKEN and CF_ACCOUNT_ID in your terminal.")
    sys.exit(1)

def main():
    print(f"🚀 Creating private Cloudflare Tunnel '{TUNNEL_NAME}' via API...")
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    resp = requests.post(url, headers=headers, json={"name": TUNNEL_NAME, "config_src": "cloudflare"})
    data = resp.json()
    
    if not data.get("success"):
        print(f"[ERROR] Tunnel creation failed: {json.dumps(data, indent=2)}")
        sys.exit(1)
        
    tunnel_id = data["result"]["id"]
    tunnel_token = data["result"]["token"]
    print(f"✅ Tunnel Created! ID: {tunnel_id}")

    print("\n🚀 Registering Cloudflare Workers VPC Service via Wrangler...")
    vpc_cmd = [
        "npx", "wrangler", "vpc", "service", "create", "dopamine-printer",
        "--type", "http",
        "--tunnel-id", tunnel_id,
        "--ipv4", "127.0.0.1",
        "--http-port", "8080"
    ]
    
    # Run wrangler command to register the VPC service to your account
    subprocess.run(vpc_cmd)

    print("\n" + "="*70)
    print("🎉 VPC PROVISIONING COMPLETE. FINAL STEPS:")
    print("="*70)
    print("1. Find the 'Service ID' output by Wrangler just above this message.")
    print("2. Paste that Service ID into your wrangler.jsonc under the PRINTER_VPC binding.")
    print("\n3. SSH into your Raspberry Pi and run this EXACT command to install the tunnel:")
    print("-" * 70)
    print(f"sudo cloudflared service install {tunnel_token}")
    print("-" * 70)
    print("Once installed, run: sudo systemctl start cloudflared")

if __name__ == "__main__":
    main()
