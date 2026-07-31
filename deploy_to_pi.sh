#!/bin/bash

# Configuration
PI_HOST="hacolby@192.168.1.9"
REMOTE_DIR="/home/hacolby/dopamine-hardware"
CF_TOKEN="eyJhIjoiYjMzMDRiMTQ4NDhkZTE1YzcyYzI0YTE0YjBjZDE4N2QiLCJ0IjoiMzc0YjRjZTMtYjMzNi00MjdjLWFjNzYtZjJjNTRhYTk3Mzc5IiwicyI6Ik56UmxaVFE1TlRndFlqWm1PUzAwT1RJNExUa3lNek10TURsaVlUbGpNVEJoT0RSbSJ9"

echo "Checking if SSH is available on $PI_HOST..."
if ! nc -z 192.168.1.9 22 2>/dev/null; then
    echo "❌ SSH port 22 is closed on 192.168.1.9."
    echo "Please enable SSH on the Raspberry Pi first."
    exit 1
fi
echo "✅ SSH is open."

echo "Syncing dopamine-hardware repository to Raspberry Pi..."
rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' ./ "$PI_HOST:$REMOTE_DIR"

echo "Running setup commands on Raspberry Pi..."
# Run the setup script using an interactive SSH session to allow sudo prompts
ssh -t "$PI_HOST" "bash $REMOTE_DIR/remote_setup.sh"

echo "--- Installing Cloudflare Service ---"
ssh -t "$PI_HOST" "sudo cloudflared service install $CF_TOKEN || echo 'Cloudflared service might already be installed'"

echo "--- Setup Complete! ---"
echo "✅ Dopamine hardware bridge is running and Cloudflare Tunnel is connected."
