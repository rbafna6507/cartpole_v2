# Interactive MuJoCo simulation

From this repository, launch the native window with one command:

```sh
uv run --locked --extra sim cartpole-v2-view
```

The entry point automatically uses `mjpython` on macOS. Linux needs a working
graphical display. You can also launch `examples/view_simulation.py` with
`mjpython` on macOS or ordinary Python on Linux.

MuJoCo's passive viewer requires `mjpython` on macOS so rendering can run on the
main thread. Ordinary Python prints the required launch command and exits.
[Official interactive viewer documentation](https://mujoco.readthedocs.io/en/stable/python.html#interactive-viewer).

The default `--start auto` starts the pole hanging down and runs the SDK's saved
reference swing-up controller. `--start upright` starts 0.04 rad from upright
with its balance controller. `--seed 7` selects the deterministic sensor seed;
`--duration 15` closes the window after 15 wall-clock seconds. Without a duration,
the window stays open until closed.

| Control | Effect |
| --- | --- |
| Space | Pause or resume simulation |
| R | Explicitly reset plant, sensors and controller to the same initial state and seed; resume |
| Esc or window close | Exit |
| Mouse and scroll | Rotate, pan and zoom the native camera |
| Tab / Shift+Tab | Show MuJoCo's native panels |

The overlay shows the selected start, explicit `simulation` source, reference
controller mode number, simulation time and running/frozen status. Controller
mode 2 is swing-up and mode 3 is balance; the saved controller can also enter
recovery modes. A rail limit, controller/plant fault, or 30 seconds of simulation
freezes the episode and clears applied forces. The overlay and console explain
the reason. Press R to restart explicitly.

This is the actual Phase 2 `MujocoBackend` and `ReferencePolicy` using explicit
simulation channels and the existing plant/model configuration. Every control
tick advances 1 ms; display frames batch those ticks at approximately 60 Hz.
Long GUI stalls slow playback without skipping controller observations. Pause
and reset discard accumulated wall-clock time.

The native GUI has its own model and data, refreshed from the authoritative SDK
backend. Native Reset/keyframe controls, physics option changes and mouse
perturbations affect this display copy only and are overwritten on the next
frame. Use R for an SDK reset. The rail and end markers are display geoms, without
contacts or changes to the simulated dynamics.

The model remains a **provisional surrogate**, without hardware identification
or validation. Successful simulated balance does not establish rig performance.
This example opens no devices and issues no hardware commands. Imports and the
controller-loop tests require no graphical display.

## macOS hang investigated on 2026-10-13

The initial demo deadlocked while updating its text overlay under `viewer.lock()`.
MuJoCo 3.15's `set_texts()` waits for the rendering thread to consume pending
text; that thread needs the same lock. Both threads therefore waited indefinitely.
Overlay calls now occur outside the lock; camera and display-data updates remain
inside it. The regression test rejects either overlay call while holding the lock.

The same native GUI probe timed out before the fix and completed afterward, with
Python 3.11.7, MuJoCo 3.15.0 and macOS 26.1 unchanged. Actual native-window checks
confirmed rendering, Space pause/resume and R reset; all 14 viewer tests passed.
The 30-second episode limit is an intentional frozen state shown in the overlay,
not this deadlock. Press R to restart.
