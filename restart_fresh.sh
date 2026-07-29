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
# Poll service status instead of fixed sleep to avoid race conditions
MAX_WAIT=10
ELAPSED=0
until sudo systemctl is-active --quiet dopamine.service || [ $ELAPSED -ge $MAX_WAIT ]; do
    sleep 0.5
    ELAPSED=$((ELAPSED + 1))
done

if sudo systemctl is-active --quiet dopamine.service; then
    echo "✅ Service restarted. Streaming logs..."
else
    echo "⚠️ Service may not be fully started yet. Streaming logs..."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
journalctl -u dopamine.service -f
