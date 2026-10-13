#!/bin/sh
set -eu
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$bundle_dir/local_repository_snapshot"
exec /home/rbafna/cartpole_inverted_pendulum/.venv/bin/python cartpole.py --text --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --preset "$bundle_dir/settings.json" "$@"
