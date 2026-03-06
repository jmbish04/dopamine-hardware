# 1. Grant permission to read input devices
sudo usermod -aG input hacolby

# 2. Activate your virtual environment
cd /home/pi/dopamine-hardware
source .venv/bin/activate

# 3. Install the evdev library
pip install evdev

# 4. Add it to requirements.txt
echo "evdev==1.7.0" >> requirements.txt

# 5. Install requirements
pip install -U pip
pip install -r requirements.txt
