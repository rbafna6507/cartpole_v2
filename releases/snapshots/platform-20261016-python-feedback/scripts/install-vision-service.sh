#!/bin/sh
# Run on Jetson after selecting a measured camera profile. Does not stop old viewers.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/cartpole-vision" "$HOME/.local/state/cartpole-vision"
if [ "$root" != "$HOME/cartpole_v2" ]; then
  echo 'Install this checkout at ~/cartpole_v2 (service uses a fixed auditable path).' >&2
  exit 1
fi
if [ ! -x "$root/.venv-vision/bin/cartpole-vision" ]; then
  echo 'First run: UV_PROJECT_ENVIRONMENT=.venv-vision ~/.local/bin/uv sync --locked --extra vision --no-dev' >&2
  exit 1
fi
if [ ! -f "$HOME/.config/cartpole-vision/runtime.env" ]; then
  cp "$root/deploy/vision/runtime.env.example" "$HOME/.config/cartpole-vision/runtime.env"
fi
cp "$root/deploy/vision/cartpole-vision.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now cartpole-vision.service
systemctl --user status cartpole-vision.service --no-pager
if [ "$(loginctl show-user "$USER" -p Linger --value)" != yes ]; then
  echo 'Service is enabled. Boot-without-login persistence additionally requires: loginctl enable-linger' >&2
fi
