#!/bin/bash

echo "🗑️  Clearing any local modifications..."
git fetch --all
git reset --hard origin/main
git clean -fd

echo "⬇️  Pulling latest code from GitHub..."
git pull origin main

echo "📦 Syncing Python dependencies..."
source /home/pi/dopamine-hardware/.venv/bin/activate
pip install -r requirements.txt

echo "🚀 Restarting Dopamine hardware bridge..."
sudo systemctl restart dopamine.service

echo "✅ System successfully synced with GitHub and restarted!"
