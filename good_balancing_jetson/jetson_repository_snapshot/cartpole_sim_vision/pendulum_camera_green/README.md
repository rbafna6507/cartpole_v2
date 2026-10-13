# Green pendulum camera tracker — Mac first, Jetson next

Tracks your green arm and black pivot screw at the narrow end. No blue marker or CNN is needed. This is a camera proof of concept with no motor commands. The round end's dark screws must NOT be selected as the pivot.

## Mac

Extract this folder, open Terminal in it, and run:

```bash
uv venv
uv pip install -r requirements-cv.txt
uv run track_camera.py --camera 0
```

Open http://localhost:8080 in a browser. If camera 0 is your built-in webcam, stop with Ctrl-C and try `--camera 1`, then 2 if needed. Allow camera access for the terminal/application running Python in macOS System Settings > Privacy & Security > Camera. Close other camera applications if capture fails. Defaults request 960x600 at30 fps; the device may negotiate something else. Resolution/FPS printed by the backend are not a latency measurement.

1. Put the entire green arm and pivot in view, with the camera facing the pendulum plane squarely.
2. **Click the black pivot screw at the NARROW end** in the browser image. Click selection follows display scaling.
3. Check the overlay: pivot circle on the black screw, other circle near the ROUND end, line along the arm.
4. Let the round end hang BELOW the pivot. Your supplied photo shows it ABOVE the pivot (upright); do not set hanging zero in that position.
5. Hold still, then click **Set hanging zero**. This needs30 detected frames within2° angular spread.
6. Swing by hand. Watch `theta_down_rad` / displayed degrees, `theta_upright_rad`, `valid`, pixel pivot position and host-read age.

Every restart requires pivot selection and a new hanging reference; old calibration is not silently reused. Clicking the pivot clears the old zero. If tracking is lost for >.3 seconds after successful acquisition, select the pivot again and re-home. Stop/restart after moving the camera or changing capture settings. The script must see the green silhouette and dark screw; hand occlusion, motion blur or similar-colored background objects can cause loss. No confident output is promised through occlusion.

## How it works / tuning

`green_arm.py` thresholds green, selects the green silhouette near your clicked pivot, searches a local area for a dark low-saturation screw, and derives arm orientation from its long axis and far-end pixels. The selected pivot disambiguates the180° axis direction. It rejects ambiguous candidates and selected screws away from the narrow end. The endpoint shown is a silhouette-derived direction feature near the round head, not a calibrated physical screw center.

Adjust `tracker.json` for your lighting/resolution: green_hsv, dark_max_value, pivot_search_radius_px, area/length thresholds. OpenCV hue range is0–179. Defaults worked on the supplied photo, but live lighting can differ. Keep the whole arm visible, avoid similarly green objects and use a short exposure for swinging. A camera mounted perpendicular to the plane is needed for this unrectified POC: zeroing does not correct perspective or lens distortion.

Theta_down=0 hanging; positive towards image-right from down. Theta_upright=wrap(pi-theta_down) matches the existing MuJoCo upright-zero convention. Verify signs against actual hardware before any future control. Pixel x is NOT meters. Angular velocity is raw finite difference, not a production filter. Lost tracking produces invalid state and clears velocity history.

## Logs and subsequent encoder comparison

`vision_runs/TIMESTAMP/angles.csv` records processed-frame sequence, monotonic host-read time, validity, angle, pivot/tip pixels and processing duration. Calibration selections are recorded in calibration_events.jsonl. Save the entire session folder.

Timestamps are taken AFTER frame read, not at exposure. The latest-frame capture thread reduces application backlog but cannot guarantee a driver has no buffering. MJPEG preview defaults15 fps and shares CPU; reduce `--preview-fps 5` if needed. `/state` marks >100 ms old data invalid; the video image itself can freeze on disconnection. Check validity and age, not only the picture. Different capture/processing rates lead to skipped frame sequences intentionally.

Encoder capture/correlation is not yet integrated. Later run camera and encoder logging on Jetson, estimate clock offset/drift or use a common visible event, and compare aligned theta. Do not equate host receipt time to exposure time. Physical cart calibration, filtered velocities, camera latency and hardware control remain future work.

## Jetson

Use the same files. Linux selects V4L2, macOS selects AVFoundation. Example (if advertised by the camera):

```bash
uv run track_camera.py --camera /dev/video0 --width 960 --height 600 --fps 80 --fourcc MJPG
```

Inspect modes with `v4l2-ctl -d /dev/video0 --list-formats-ext`. FourCC is only set on Linux; macOS negotiates its format. If pip lacks an OpenCV wheel for JetPack, use distro python3-opencv/numpy/flask in a system-site-packages venv instead.

To watch Jetson from your computer over Tailscale, run on your computer:

```bash
ssh -N -L 8080:127.0.0.1:8080 YOUR_USER@JETSON_TAILSCALE_IP
```

Then browse http://localhost:8080. SSH must allow forwarding. Alternatively bind `--bind JETSON_TAILSCALE_IP` and view that IP directly if your tailnet/firewall allows it. Server has no login; trusted tailnet only, no public exposure. Tracking runs locally, not through the remote preview.

## Validation

Detection was checked on your supplied photo and transformed copies (rotation/translation), with lost-frame behavior tested. Python syntax was checked. This is not a live Mac/Jetson camera or timing validation. Existing state simulator is unchanged and remains in its separate package.

OpenCV backend reference: https://docs.opencv.org/doc/doxygen/html/d4/d15/group__videoio__flags__base.html
