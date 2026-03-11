#!/bin/bash
# Restart Fresh Script for Dopamine Hardware Bridge
# This script:
# 1. Pulls latest code from git
# 2. Restarts the systemd service with fresh code
# 3. Streams the logs in real-time

set -e  # Exit on error

echo "🔄 Pulling latest code from git..."
git pull

echo "🔄 Restarting dopamine.service..."
sudo systemctl restart dopamine.service

echo "⏳ Waiting for service to start..."
sleep 2

echo "✅ Service restarted. Streaming logs..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
journalctl -u dopamine.service -f
