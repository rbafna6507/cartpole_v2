#!/bin/sh
# Camera/HTTP/UDP only. This script never opens a serial device.
set -eu
cd "${VISION_ROOT:-$HOME/cartpole_v2}"
set --
if [ -n "${VISION_VIEW_BIND:-}" ]; then set -- --view-bind "$VISION_VIEW_BIND" --view-port "${VISION_VIEW_PORT:-3091}"; fi
if [ -n "${VISION_VIEW_TCP_MSS:-}" ]; then set -- "$@" --view-tcp-mss "$VISION_VIEW_TCP_MSS"; fi
exec .venv-vision/bin/cartpole-vision "$@" \
  --camera "${VISION_CAMERA:-/dev/v4l/by-id/usb-Arducam_Arducam_B0495__USB3_2.3MP__Arducam_202500915_0001-video-index0}" \
  --width "${VISION_WIDTH:-960}" --height "${VISION_HEIGHT:-600}" --rotate "${VISION_ROTATE:-180}" \
  --fps "${VISION_FPS:-30}" --video-fps "${VISION_VIDEO_FPS:-30}" --video-bitrate "${VISION_VIDEO_BITRATE:-4000}" \
  --detector-width "${VISION_DETECTOR_WIDTH:-640}" --port "${VISION_PORT:-3090}" \
  --encoder-port 3096 --sdk-port 3097 --camera-timeout 2 --keep-sessions 4 \
  --calibration-file "${VISION_CALIBRATION:-$HOME/.local/state/cartpole-vision/calibration.json}" \
  --out "${VISION_OUTPUT:-$HOME/.local/state/cartpole-vision/sessions}" \
  --log-file "${VISION_LOG:-$HOME/.local/state/cartpole-vision/runtime.log}"
