#!/bin/bash

echo "updating permissions"
sudo usermod -aG lp hacolby
sudo usermod -aG dialout hacolby

echo "kill the default linux driver"
sudo rmmod usblp

echo "reload the trigger"
sudo udevadm control --reload-rules
sudo udevadm trigger
