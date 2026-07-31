#!/bin/bash
set -e

PI_HOST="hacolby@192.168.1.9"

echo "Syncing updated hardware code and Cloudflare credentials to Raspberry Pi..."
scp -o StrictHostKeyChecking=no dopamine.service hardware.py "$PI_HOST:/tmp/"

echo "Applying updates and restarting dopamine..."
ssh -t "$PI_HOST" "set -e; \
    sudo cp /tmp/hardware.py /home/hacolby/dopamine-hardware/hardware.py; \
    sudo chown hacolby:hacolby /home/hacolby/dopamine-hardware/hardware.py; \
    sed -i 's|/home/pi/|/home/hacolby/|g' /tmp/dopamine.service; \
    sudo cp /tmp/dopamine.service /etc/systemd/system/dopamine.service; \
    sudo systemctl daemon-reload; \
    sudo systemctl restart dopamine.service; \
    echo '✅ Hardware scanner logic and service updated successfully!'"
