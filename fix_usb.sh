#!/bin/bash

# Configuration
PI_HOST="hacolby@192.168.1.9"
REMOTE_DIR="/home/hacolby/dopamine-hardware"

echo "Syncing dopamine-hardware repository to Raspberry Pi..."
rsync -avz -e "ssh -o StrictHostKeyChecking=no" --exclude '.git' --exclude '.venv' --exclude '__pycache__' ./ "$PI_HOST:$REMOTE_DIR"

echo "Running USB setup commands on Raspberry Pi..."
# Run the setup script using an interactive SSH session to allow sudo prompts
ssh -t "$PI_HOST" "set -e; \
    echo '--- Installing udev rules ---'; \
    sudo cp /home/hacolby/dopamine-hardware/99-escpos.rules /etc/udev/rules.d/; \
    echo '--- Running USB permissions script ---'; \
    sudo usermod -aG lp hacolby; \
    sudo usermod -aG dialout hacolby; \
    sudo usermod -aG input hacolby; \
    sudo rmmod usblp || true; \
    sudo udevadm control --reload-rules; \
    sudo udevadm trigger; \
    echo '--- Restarting dopamine service ---'; \
    sudo systemctl restart dopamine.service; \
    echo '✅ USB permissions configured.'"
