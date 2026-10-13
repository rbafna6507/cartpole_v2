# Cartpole simulation, PPO and Jetson vision

This package extends the previous local MuJoCo/PPO starter. Nothing here sends motor commands. It is a simulation baseline and camera proof of concept, not a hardware-ready controller.

## Simulation: computer or Colab

Use Python 3.10+ in a fresh environment. From this directory:

```bash
python -m pip install -r requirements-sim.txt
python train_state.py --smoke --out results/smoke
python train_state.py --task balance --steps 1000000 --out results/balance
python evaluate.py results/balance --episodes 30 --html
```

Open the generated replay HTML without OpenGL. Evaluation saves duration, failure and upright fraction on separate seeds. The smoke run checks software, not learning. Training budgets are starting points, not convergence guarantees. CPU is the default. After reliable balance, try:

```bash
python train_state.py --task swingup --load results/balance --steps 2000000 --out results/swingup
python evaluate.py results/swingup --episodes 30 --html
```

Continue a policy only with compatible observation/action scaling. The environment is single-pole; model builder 2/3-link structures are examples needing new environments, parameters and training. `train_colab.ipynb` includes upload, training, replay and results download.

### Assumptions and system ID

Edit `simulation.json`. Geometry follows recent firmware comments: 125 mm rod, 11.05 g rod and 11.7 g combined tip mass, all awaiting confirmation. Earlier 100 mm assembly logs are not silently applied. Metadata records NEMA17, 12 V and 60 teeth. With 2 mm belt pitch, travel/rev=120 mm and 200 steps/rev ×16 microsteps gives 26.6667 pulses/mm. Verify pitch and driver settings.

UNMEASURED placeholders: cart mass .5 kg, velocity-servo gain 20 N/(m/s), force cap 2 N, v_max .25 m/s, a_max 1 m/s², joint friction zero. Rail half travel .2 m assumes 400 mm usable total. Change to measured travel; episode termination is 20 mm inside each end. Supply voltage is metadata, not an electrical motor model. The force-limited velocity servo does not model stepper phases, missed steps, speed-dependent torque or the Teensy jerk limiter. Calibrate/extend before transfer.

Use the characterization package's `lab.py export-model` with measured complete rotating mass and COM, then:

```bash
python train_state.py --sysid measured_model.json --task balance --out results/measured
```

The export supplies mass, COM, pivot inertia, viscous damping and dry friction. Separately update geometry/cart/drive/rail in simulation.json. Validate passive motion against held-out releases and driven motion against independently measured cart trajectories.

Physics step .5 ms; policy 12.5 ms (80 Hz). Action [-1,1] requests acceleration, integrated into a bounded velocity target. Observation: `[x/rail_stop, xdot/v_max, sin(theta), cos(theta), omega/20, target_velocity/vmax]`. Theta=0 upright; positive leans toward world +x. Reward encourages upright posture and centering with action penalties. Rail exit or excessive balance-task tilt terminates; horizon 10 seconds. This is perfect-state training; measured noise, delays, dropouts and domain variation remain follow-up work before transfer.

## Jetson camera: no CNN required

Use two lightweight matte colored markers: green centered on pivot axis and blue centered near the arm tip. Keep other green/blue objects out of view. OpenCV thresholds HSV colors, extracts contours and finds centroids. Mount the camera perpendicular to the motion plane with the entire swing/rail visible. Marker mass should be included in system ID if significant.

```bash
sudo apt-get install v4l-utils python3-venv
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
python3 -m venv .venv-cv
source .venv-cv/bin/activate
python -m pip install -r requirements-cv.txt
python track_camera.py --camera /dev/video0 --width 960 --height 600 --fps 80 --fourcc MJPG
```

Use an advertised camera mode. MJPG and 80 fps are requests, not guarantees; use `--fourcc YUYV` if appropriate. The script prints negotiated settings and reports processed FPS. USB/V4L2 capture, not CSI/Argus. If your JetPack/Python lacks pip wheels, use apt packages `python3-opencv python3-numpy python3-flask` with a `--system-site-packages` venv instead; avoid conflicting cv2 installs. No CUDA/PyTorch needed for vision.

### View from your computer over Tailscale

Default bind is Jetson localhost. With SSH access to the Jetson, run ON YOUR COMPUTER:

```bash
ssh -N -L 8080:127.0.0.1:8080 YOUR_USER@JETSON_TAILSCALE_IP
```

Open http://localhost:8080. If local 8080 is occupied use local 8081 in the tunnel and browser. SSH access policy must permit TCP forwarding.

Alternatively get Jetson's IP with `tailscale ip -4` and bind only that address:

```bash
python track_camera.py --bind 100.X.Y.Z --port 8080
```

Browse http://100.X.Y.Z:8080 on your computer. Tailnet rules and host firewall must permit the port. POC server has no login; use only a trusted tailnet, no public exposure/Funnel. Anyone allowed access can change vision calibration. No hardware actuation is exposed.

### Home and track

1. Verify overlay circles follow the correct markers.
2. Let the arm hang still and click **Set hanging zero**.
3. Homing requires 30 consecutive detected frames with <=2° angular spread. You assert gravity-down; a stationary held angle cannot be distinguished automatically.
4. Move the pole and watch signed theta from hanging, upright-zero theta and tracking validity.
5. Check physical angles with a protractor, especially ±20°, ±45°, ±75°. Edit HSV thresholds in tracker.json if needed, then restart. Multiple same-color blobs invalidate detection rather than silently selecting another object.

Calibration saves to tracker.json. Re-home after changing camera position, image orientation/resolution or markers. Clear calibration if old length gating interferes. The vector `(dx,dy)` is pivot→tip with image y downward. `a=atan2(dx,dy)`, `theta_down=wrap(a-home)` and `theta_upright=wrap(pi-theta_down)`. This matches MuJoCo positive rotation upright→right; verify image right matches hardware +x before control. Homing removes camera roll but DOES NOT correct perspective, lens distortion or unequal pixel scale. Lens calibration and planar homography are needed for accurate non-perpendicular views.

`/state` provides JSON; `/stream` provides annotated MJPEG. `vision_runs/TIMESTAMP/angles.csv` saves host-read timestamps, sequence, pixel positions, angles, angular rate and processing duration. Missing/ambiguous markers invalidate state; first sample after loss has omega=null. HTTP state older than100 ms is invalidated. Frozen preview alone is not evidence of tracking. Angular rate is noisy finite difference, not a production observer; changes over pi between frames alias.

Capture drains frames in a thread; processing consumes the latest frame and intentionally skips intermediate frames when overloaded. Preview runs at15 fps, adjustable with `--preview-fps 5`; benchmark CPU load with preview on/off. Timestamps are taken AFTER OpenCV read, not at exposure. Buffer-size=1 is only a request. Processed FPS/host age do not measure true exposure-to-state latency.

Local Jetson tracking does not depend on remote video delivery. Future state policy should also run locally. This POC supplies angle and pixel pivot location, NOT calibrated cart meters or filtered velocities. Do not feed pixel x or down-zero theta directly into policy observations. Add spatial calibration, temporal estimation, encoder comparison and latency measurement first.

## What is still needed

- Current characterization runs ZIP, assembly revision, complete rotating mass/COM, rod and screw-center distances.
- Moving cart mass, measured usable travel, belt pitch/microsteps and ruler displacement checks.
- Exact motor part number, driver/current setting, 12 V supply and measured speed/acceleration/braking/tracking. NEMA17 is a frame size, not a torque specification.
- Jetson model/JetPack, camera exact model and supported modes.
- Vision logs and synchronized encoder/video comparison. Use matched clocks or a shared observable event; host receipt times alone cannot establish camera latency.

No wiring changes are required. Existing Teensy characterization firmware stays separate. Next validate simulation, train baseline, calibrate visual state and measured timing, add simulation imperfections, then shadow-test an explicit bounded-command hardware interface. For multiple poles measure and observe every link: camera segment orientations are absolute while later MuJoCo hinge angles are relative to parents.

References: https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html ; https://mujoco.readthedocs.io/en/latest/XMLreference.html ; https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html ; https://tailscale.com/docs/reference/ssh-over-tailscale
