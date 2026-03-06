import os
import subprocess
import sys

def run_cmd(cmd):
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"Error executing command: {result.stderr}")
    return result.stdout

def install_cloudflared(token):
    print("--- Installing Cloudflared (ARM64) ---")
    # Download the latest cloudflared for Raspberry Pi (ARM64)
    run_cmd("curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb")
    
    # Install the package
    run_cmd("sudo dpkg -i cloudflared.deb")
    
    print("--- Configuring Cloudflared Service ---")
    # Install the service using the provided token
    run_cmd(f"sudo cloudflared service install {token}")
    
    print("--- Starting Service ---")
    run_cmd("sudo systemctl enable cloudflared")
    run_cmd("sudo systemctl start cloudflared")
    run_cmd("sudo systemctl status cloudflared --no-pager | head -n 10")
    print("\n✅ Cloudflare Tunnel is now installed and running as a systemd service.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 setup_tunnel.py <YOUR_CLOUDFLARE_TUNNEL_TOKEN>")
        sys.exit(1)
        
    token = sys.argv[1]
    install_cloudflared(token)
