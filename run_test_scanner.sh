#!/bin/bash
set -e

PI_HOST="hacolby@192.168.1.9"

echo "Syncing test script to Raspberry Pi..."
scp -o StrictHostKeyChecking=no test_scanner.py "$PI_HOST:/home/hacolby/dopamine-hardware/"

echo ""
echo "=================================================="
echo "      🚀 DOPAMINE SCANNER TEST ENVIRONMENT"
echo "=================================================="
echo ""
echo "This will temporarily stop the background service to"
echo "allow direct access to the scanner. When you press Ctrl+C,"
echo "the service will automatically restart."
echo ""
echo "Connecting to Pi..."

ssh -t -o StrictHostKeyChecking=no "$PI_HOST" "
    echo 'Stopping dopamine.service...'
    sudo systemctl stop dopamine.service
    
    echo 'Starting test script...'
    /home/hacolby/dopamine-hardware/.venv/bin/python /home/hacolby/dopamine-hardware/test_scanner.py
    
    echo 'Restarting dopamine.service...'
    sudo systemctl start dopamine.service
    echo '✅ Background service restored.'
"
