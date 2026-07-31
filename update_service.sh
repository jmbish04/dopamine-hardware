#!/bin/bash
set -e

PI_HOST="hacolby@192.168.1.9"

echo "Syncing dopamine.service with Cloudflare credentials to Raspberry Pi..."
scp -o StrictHostKeyChecking=no dopamine.service "$PI_HOST:/tmp/dopamine.service"

echo "Applying service file and restarting dopamine..."
ssh -t "$PI_HOST" "set -e; \
    sed -i 's|/home/pi/|/home/hacolby/|g' /tmp/dopamine.service; \
    sudo cp /tmp/dopamine.service /etc/systemd/system/dopamine.service; \
    sudo systemctl daemon-reload; \
    sudo systemctl restart dopamine.service; \
    echo '✅ Service updated and restarted successfully!'"
