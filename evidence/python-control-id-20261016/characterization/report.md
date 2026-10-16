# Bounded characterization harness — prepared, not run on hardware

`characterize.py` implements the requested trusted SDK experiment. Only its
explicit `--execute` branch opens a rig. This preparation used local numerical
tests and an offline PTY protocol fixture; no physical serial device, service,
calibration, parameter, switch configuration, or home was changed.

The controller runs through `run_policy` at **100 Hz**, using exactly cart step
position/velocity and pole magnetic angle/angular velocity. It requests
`a_ref + 80*(x_ref-x) + 14*(v_ref-v)`, clamped to **±1 m/s²**. The executor retains
its existing governor and live parameters.

| Selection | Amplitude per tone | Frequencies | Certified reference peaks: position / velocity / acceleration |
|---|---:|---|---|
| `pilot` | 1.25 mm | 0.8, 1.3, 2.1 Hz | 3.2468 mm / 0.033007 m/s / 0.308298 m/s² |
| `train` | 2.5 mm | 0.8, 1.3, 2.1 Hz | 6.4936 mm / 0.066014 m/s / 0.616596 m/s² |
| `heldout` | 2 mm | 0.7, 1.6, 2.3 Hz | 5.1689 mm / 0.057845 m/s / 0.625541 m/s² |

Each reference is a 20 s multisine with 2 s quintic ramps. Position, velocity and
acceleration are zero at both endpoints. The taper is C2; jerk may jump at the
interior ramp joins. Bounds use a 0.1 ms grid plus analytic derivative bounds
between grid points. They bound the reference, not the actual physical motion.
The exact calculation is in `waveform-bounds.json`.

Before arming, the harness reads the complete live parameter catalog and encoder
metadata. It requires saved reference 330, valid encoder configuration, switches
on, healthy homed state, disabled/stopped mode, no governor brake, and 0.5 s of
quiet hanging observations. The explicit quiet limits are |x|<3 mm, |v|<5 mm/s,
|a|<0.1 m/s², |omega|<0.15 rad/s, wrapped distance to down <0.35 rad, and no more
than 0.03 rad of drift over that preflight window. Failure stops; it never waits
through unapproved motion or implicitly rehomes.

During execution, the policy stops on |x|>30 mm, |v|>0.12 m/s, wrapped departure
from the initial hanging angle >0.65 rad, or |omega|>6 rad/s. Both board timestamp
gaps and host policy-call gaps must be <20 ms; replay, wrong session, missing or
invalid channels, stale effective timestamps, and incoherent channel snapshots
also fail. Health, homing and switch flags are checked on the same state snapshot
that supplies the four policy values. Host receipt freshness is also checked by
the SDK. All failure paths call STOP; the normal SDK runner also stops in its
`finally` block.

`--tail` requests a nominal 20 s **zero acceleration command** tail after the
taper. Entry requires |x|<3 mm and |v|<5 mm/s before switching to the tail, with a
healthy board. The general trajectory and timing guards remain active. This is
recorded as `commanded_hold`; it is not independent proof that the physical cart
is fixed. Zero acceleration can retain nonzero commanded velocity. There is no
position feedback during the tail. A bounded 30 ms zero-command completion pad
allows the endpoint to be sampled despite the SDK runner's 10 ms early wall
deadline; it adds no excitation. Maximum requested lease duration is 40.03 s.

The SDK JSONL includes raw state/action records, all live parameters and metadata,
and `characterization_reference` rows with x/v/a/jerk reference, observed state,
unclamped and clamped command, phase, board sequence/time, and host policy time.
Optional `--record-gc` records GC events without changing GC settings. The final
report records raw-log SHA256, dropped-record count, failures and source hashes.
Existing output directories are refused so separate pilot/train/heldout records
cannot overwrite one another.

Offline verification:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover \
  -s evidence/python-control-id-20261016/characterization \
  -p test_characterize.py -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/python-control-id-20261016/characterization/characterize.py --check-waveform
```

**13 local tests passed** on Python 3.11.7. These cover endpoint/derivative math,
continuous reference bounds, a complete 40 s synthetic tracking sequence,
actual-state guards, wrapping, timing/stale/session errors, tail refusal,
preflight, explicit CLI requirements, failure cleanup, and real SDK framing over
a local PTY. The protocol test reads all 41 parameters, sends five bounded
20 ms-TTL actions at 100 Hz, then observes x=31 mm and verifies STOP. It verifies
no parameter writes or HOME/CENTER/CLEAR/SWITCHES/MODE/REHOME operations. No broader
repository test suite or hardware test was run for this evidence-only change.

For the parent/operator's review only, the eventual invocation has this form
(not executed during preparation):

```sh
.venv/bin/python evidence/python-control-id-20261016/characterization/characterize.py \
  --execute --kind pilot --port "$RIG_PORT" --log-dir "$NEW_RUN_DIRECTORY" \
  --record-gc
```

Choose train or heldout explicitly for later distinct runs. Do not change the
identification acceptance gates or estimate a new zero angle from heldout data.
These command and encoder observations still cannot independently establish
cart tracking, physical masses, motor force, or true stationary-cart passive
dynamics. The prior system-ID assessment remains rejected.
