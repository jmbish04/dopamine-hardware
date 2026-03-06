# 1. Grant permission to read input devices
sudo usermod -aG input hacolby

# 2. Activate your virtual environment
cd /home/pi/dopamine-hardware
source .venv/bin/activate

# 3. Install the evdev library
pip install evdev

# 4. Add it to requirements.txt
echo "evdev" >> requirements.txt

# 5. Install requirements
pip install -U pip
pip install -r requirements.txt

# 6. Reload hardware rules
sudo udevadm control --reload-rules && sudo udevadm trigger
