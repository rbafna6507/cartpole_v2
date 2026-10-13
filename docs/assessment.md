# Existing software assessment

Inspected locally on 2026-10-12. No Jetson connection, live camera access, hardware
command, firmware upload, or change to existing source was performed.

## What is worth retaining

| Source in `../cartpole` | Useful work | Required v2 changes |
|---|---|---|
| `vision/pendulum_vision/detector.py` | Green-shaft geometry, circular end/pivot disambiguation, rejection reasons | Headless adapter, versioned detector configuration, explicit single-link capability |
| `vision/pendulum_vision/state.py` | Calibration gates, independent angle/cart validity, causal derivatives, effective timestamps | Explicit coordinate transform, calibration identity, clock identity, per-field validity |
| `vision/pendulum_vision/cart.py` | Independent cart patch tracking during arm occlusion | Port when replay accepts recorded patch/calibration events; do not silently select a patch |
| `vision/pendulum_vision/capture.py` | Latest-frame acquisition and bounded recording | Later live milestone; preserve driver/exposure timestamp semantics and single acquisition owner |
| `vision/pendulum_vision/replay.py` | Actual-video regression path and timestamp sidecars | Preserve original frame/sequence/time origins, headless output, strict provenance |
| `deployment/firmware/deployment_executor/` | Local pulse generation, bounds, observation-anchored command expiry, sessions, faults | Physical limits/inhibit integration and bench verification; reconsider mandatory policy-encoder coupling |
| `deployment/src/cartpole_deploy/protocol.py`, `hardware.py` | CRC framing, finite values, freshness, ownership-aware close, no action retry | Trusted broker/operator use only; incompatible with current legacy firmware |
| `deployment/src/cartpole_deploy/model.py`, `simulation.py` | Explicit inertia, bounded actuator, governor parity tests | Measured rig configuration; multi-link model; sensor timing/noise/dropout models |
| `deployment/src/cartpole_deploy/identification.py` | Passive effective-length/damping fit, holdout validation, hashes | Synchronized external cart measurement, driven fits, uncertainty and identifiability |
| `deployment/src/cartpole_deploy/gym_env.py` | Gymnasium integration and seeded tests | It is an upright-balance scaffold; swing-up/recovery tasks and image observations are separate work |
| `deployment/docs/internet.md` | Local policy execution, trusted broker, outbound job worker, narrow permissions | Services, queue, artifact loader and hostile-code isolation remain unimplemented |

All **52 files** covered by `deployment/MANIFEST.json` match their saved hashes.
This makes it a useful reproducible starting point. It does not establish hardware
readiness. A separate source inventory records the exact files read for this plan.

## Concrete gaps

1. **No common sensor contract.** Deployment assumes one encoder and one scalar
   pendulum state. Vision emits dictionaries with different validity/time fields.
   Neither currently defines interchangeable raw, derived, and fused observations.
2. **Host arrival is not exposure time.** Camera timestamps are recorded after
   `VideoCapture.read()`. The velocity estimator fits up to 80 ms of history and
   reports an effective time roughly 20–40 ms behind the latest angle sample.
3. **Vision accuracy remains unmeasured.** The saved stationary benchmark is near
   80 FPS. The broader motion reanalysis reports 94.8% detection coverage, including
   stationary periods. These are not fast-swing accuracy or control-latency claims.
4. **Cart motion is not independently measured by firmware.** `x/v/a` are emitted
   steps and governed profile values. Belt slip, missed steps and external movement
   can invalidate the inferred physical position.
5. **Physical limits are not implemented in the deployment executor.** PCB notes
   identify potential switch inputs on pins 26–29, but this does not establish
   installed wiring, tested switches, or a working emergency inhibit. Pin 8 enables
   the cart and Z drivers together; v2 must preserve the implications of that wiring.
6. **Current model parameters are provisional.** The deployment profile is a
   historical 125 mm assembly, with assumed cart mass, COM and drive dynamics.
   The current assembly and active calibration must be recorded at handoff.
7. **Encoder reliability needs a dated commissioning result.** Earlier local
   investigation records large repeatability shifts. Later tuning files exist;
   the live session may have resolved or changed that state. Treat the earlier
   finding as historical evidence, not a statement of the current running rig.
8. **Public uploads are an unimplemented security boundary.** A Python process,
   an ONNX file, and a container are not by themselves assurance against hostile
   code or resource exhaustion. Isolation must be tested on the selected Jetson OS.
9. **Multi-link support is structural work.** The detector and model are single
   pendulum implementations. Three-element arrays alone do not solve link identity,
   occlusion, joint sensing, changing dynamics, or a larger physical swept volume.

## A misleadingly passive tool

`passive_capture.py:PassiveSession.__init__` opens a serial link, sends `stop`,
then `rate 100` and `params`. Those actions are appropriate for its standalone
operator workflow but would disrupt another controller. It was read, not run.
Future read-only subscribers must consume copies from the single owner, without
changing stream rate or stopping the owner on disconnect.

## Verification performed in this assessment

| Check | Fresh result | Scope |
|---|---|---|
| `vision`: `../.venv/bin/python -m unittest discover -s tests -q` | 33 tests passed | Synthetic scenes, fixture images, state, capture mocks, replay and API tests; no camera opened |
| `deployment`: selected config/protocol/identification/recording tests | 20 tests and 22 subtests passed under pytest | Local numerical and protocol tests; no device connection |
| `deployment`: `sh tests/native/run.sh` | 9 executor groups and sketch integration tests passed | C++ host stubs with address/undefined-behavior sanitizers; no board connected |
| Deployment source manifest | 52/52 hashes match | Saved source identity |
| Existing motion excerpt replay | 498/650 frames accepted (76.6%); no timestamp fallback | 8.376 s file with original timestamp sidecar; no physical calibration assumed |

Selected pytest command used the existing interpreter explicitly:

```sh
cd /Users/rbafna/projects/cartpole/deployment
/Users/rbafna/.pyenv/versions/3.11.7/bin/python3 -m pytest -q \
  tests/test_config.py tests/test_protocol.py \
  tests/test_identification.py tests/test_recording.py
```

The root venv lacks pytest. Interpreter selection also varies with working
directory. MuJoCo and Gymnasium are absent from the inspected interpreters, so
the full simulation/CLI suite was **not rerun**. Hardware loopback tests were
also not rerun. The older 85-test report in deployment is historical evidence,
not this session's result. No environment was installed or modified.

Fresh replay detector processing measured 4.77 ms median and 5.52 ms p95 on this
Mac. This excludes full sensor-to-controller latency. The longest completed
rejection interval was 1.355 s, measured from first rejected frame to next accepted
frame. Visual review of the contact sheet shows hand occlusion during the long
loss and visible blur during swings. The 76.6% excerpt coverage and historical
94.8% whole-recording coverage have different denominators and are not contradictory.
Neither measures accuracy or swing-only reliability. The replay's uncalibrated
angle/cart fields remain invalid rather than assuming a hanging reference.

Artifacts: [summary](../evidence/replay-baseline/summary.json),
[dropout analysis](../evidence/replay-baseline/dropout-analysis.json),
[contact sheet](../evidence/replay-baseline/contact.jpg),
[overlay video](../evidence/replay-baseline/overlay.avi).

## Migration method

Keep the original repository intact. Import only the components needed by each
milestone, along with their relevant tests and source hashes. Archive an exact
deployment snapshot during implementation; do not expose its hardware CLI as
the new public SDK. Do not copy live logs, build outputs, environments or secrets.
Large videos remain external inputs; small redistributable fixtures can be added
with their provenance and labels. License selection is needed before public release.
