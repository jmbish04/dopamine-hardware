#!/bin/bash
sudo apt-get install alsa-utils -y
sudo raspi-config nonint do_audio 1
