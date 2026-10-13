# Update: rotation and cart derivatives

For your upside-down Arducam on Mac:

```bash
uv venv
uv pip install -r requirements-cv.txt
uv run track_camera.py --camera 1 --rotate 180 --fps 80
```

Open http://localhost:3080. Change camera index if needed. Rotation choices are0,90,180,270 degrees clockwise. Software rotation is applied BEFORE detector, calibration, preview and CSV coordinates. Do not also enable camera-side flipping. Pivot and rail references must be selected again after rotation/camera changes. Capture width/height refer to the unrotated camera mode.

Jetson example:

```bash
uv run track_camera.py --camera /dev/video0 --rotate 180 --fps 80 --fourcc MJPG
```

The page now plots theta, cart position, cart velocity and cart acceleration. Position is the calibrated pivot-center translation. Velocity and acceleration are estimated by fitting a quadratic to the latest up-to12 positions within150 ms, evaluating derivatives at the newest sample. At least5 samples spanning25 ms are required; outputs are null while warming up or after loss/calibration reset. `derivative_window_s` records the actual interval. These are causal, smoothed estimates, still sensitive to image jitter/model error; not measured force or motor acceleration, and not validated feedback signals. No physical acceleration clipping is applied. Compare against an independent reference before control. Theta velocity remains the earlier finite difference.

CSV includes `cart_x_mm`, `cart_x_m`, `cart_v_mm_s`, `cart_v_m_s`, `cart_a_mm_s2`, `cart_a_m_s2`. Browser plots are display-rate; CSV is processed-frame-rate. Rotation is recorded in session.json. Firmware/encoder synchronization is not implemented here.

Hardware flip controls depend on USB camera firmware. On Jetson inspect `v4l2-ctl -d /dev/video0 --list-ctrls`; do not assume controls from a MIPI AR0234 driver apply to the USB camera. Software rotation works without those controls.

The included ../cartpole.py is the user's supplied SERIAL console unchanged, with its missing angle_plot.py helper. It has no Ethernet support yet because the current firmware attachment is missing. Do not use it against characterization firmware's different protocol. The camera script is independent of this console.

---

# Green pendulum: theta and cart position plots

This extends the working green-arm tracker. No firmware or motor commands are included. The pivot screw is rigidly attached to the cart, so its tracked center measures cart translation even as the pendulum rotates. A separate detector of the cart's gray bracket is unnecessary. Detection still requires the green arm and dark pivot to be visible; occlusion can invalidate both measurements.

## Start on Mac with the Arducam

From this directory:

```bash
uv venv
uv pip install -r requirements-cv.txt
uv run track_camera.py --camera 1 --width 960 --height 600 --fps 80
```

Open **http://localhost:3080**. Try camera 0 or2 if1 is not the Arducam. Allow camera access for your terminal application. Camera settings are requests; inspect negotiated settings and processed_fps. A lower rate is fine to first check detection. Mac uses AVFoundation and negotiates pixel format; Linux uses V4L2.

## Set up angle and cart position

1. Click the black pivot screw at the narrow end. Verify the line follows the green arm toward its round end.
2. Let the round end hang BELOW the pivot, then click **Set hanging zero**. Your earlier photo showed the arm upright, not hanging.
3. Mark two known cart positions with a ruler, preferably widely separated within usable travel. These are pivot/cart-center positions, not the rail's overall length. You need not touch mechanical end stops.
4. Move the cart slowly to the left mark, hold still with pivot visible for at least20 processed frames, then click **Record left A**.
5. Move slowly to the right mark, hold still, enter the actual separation in millimeters, then click **Record right B**.
6. The midpoint between A and B is x=0, A is -separation/2, B is +separation/2. The two live plots show theta in degrees and cart x in mm over20 seconds. Check an intermediate ruler position to verify the scale.

If tracking is lost, click the pivot again and re-home theta. Existing cart references are retained during reselection for the same fixed camera view. If the camera, resolution or image orientation changes, click **Clear cart calibration** and redo both references. All calibration starts fresh on program restart. Re-recording A clears B; recording B completes the new scale. Recalibration clears browser graph history; every calibration event is saved alongside the full CSV.

Cart calibration is an affine projection onto the image line A→B, which handles camera roll but not perspective or lens distortion. Mount the camera perpendicular to the motion plane, and validate intermediate positions. Positions outside the calibrated extent or too far from the rail line are invalidated; the script does not extrapolate. Small jitter at endpoints can cross the validity boundary. A planar homography/lens calibration remains needed for precise oblique views. This is not yet a calibrated control-state observer.

## Plots and files

- Browser plots: up to10 Hz display samples, rolling20 seconds; theta wraps at±180°. Gaps indicate invalid, stale, missing or disconnected data. No remote plotting dependency/CDN.
- `vision_runs/TIMESTAMP/angles.csv`: every processed frame, host-read timestamp, raw angle, pixel pivot/tip, cart validity, cart x in mm AND meters, and estimated cart speed/acceleration in mm/s and mm/s².
- `cart_calibration.json`: pixel reference points and measured span. `calibration_events.jsonl`: timestamped reference/zero changes.
- Pixel position is available before physical calibration; the mm plot remains empty until both references are set. Cart validity is separate from theta validity.

After stopping capture with Ctrl-C, create a full-rate scientific plot:

```bash
uv run --with matplotlib plot_session.py vision_runs/YOUR_SESSION/angles.csv
```

This writes `position_theta.png` alongside the CSV. Send the entire session folder for analysis.

No smoothing is applied to positions/angles. Derivative estimates are noisy; they are not ready for policy input. Camera timestamps are host times after read, not exposure timestamps. Processing intentionally takes the newest frame and may skip frames. JPEG preview shares CPU; lower `--preview-fps 5` if needed. Browser state older than100 ms invalidates cart and angle values. Full-rate logs preserve actual host timing gaps. Validate camera exposure latency and accuracy before control.

## Jetson and remote preview

Same files, Linux device path (use an advertised mode):

```bash
uv run track_camera.py --camera /dev/video0 --width 960 --height 600 --fps 80 --fourcc MJPG
```

Use `v4l2-ctl -d /dev/video0 --list-formats-ext` to inspect supported modes. If pip wheels are unavailable on your JetPack, use distro python3-opencv/numpy/flask with a system-site-packages venv. Camera/encoder synchronization is future work; logs from independent clocks need offset/drift alignment.

On your computer to view Jetson via Tailscale:

```bash
ssh -N -L 3080:127.0.0.1:3080 YOUR_USER@JETSON_TAILSCALE_IP
```

Open http://localhost:3080. Server binds localhost by default; no public exposure or motor control. An explicit tailnet bind is possible with --bind but provides no application login.

## Validation

Cart calibration math checked with an angled image rail: endpoint/midpoint position, known velocity, out-of-range rejection, tracking-loss reset and unstable reference rejection. Offline PNG generation and Python syntax checked. Original arm detector was validated against your photo in the preceding version. Live Arducam, browser rendering and physical accuracy are not tested here.
