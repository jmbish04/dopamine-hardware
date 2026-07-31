#!/bin/bash
set -e

echo "--- Updating and installing dependencies ---"
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv rsync curl git

echo "--- Setting up Python virtual environment ---"
cd /home/hacolby/dopamine-hardware
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "--- Fixing dopamine.service paths and user ---"
sed -i 's|/home/pi/|/home/hacolby/|g' dopamine.service

echo "--- Installing systemd service ---"
sudo cp dopamine.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dopamine.service
sudo systemctl restart dopamine.service

echo "--- Installing Cloudflared ---"
if ! command -v cloudflared &> /dev/null; then
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
    sudo apt-get update && sudo apt-get install -y cloudflared
fi
