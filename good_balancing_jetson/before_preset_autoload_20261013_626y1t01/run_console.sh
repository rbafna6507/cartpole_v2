#!/bin/sh
cd /home/rbafna/good_balancing_jetson/local_repository_snapshot || exit 1
exec /home/rbafna/cartpole_inverted_pendulum/.venv/bin/python cartpole.py --text --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 "$@"
