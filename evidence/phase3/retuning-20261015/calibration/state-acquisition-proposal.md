# Native-count acquisition without reflashing or changing reference 370

This is a read-only acquisition design and local source/format audit. It changes
no production code, firmware, reference, calibration approval, or hardware state.
The v4 release archive at `/tmp/cartpole-retune-20261015/rehome-release.tar.gz`
contains source and HEX members whose hashes match its release manifest. The
source/HEX fingerprints are recorded in `state-raw-decode-audit.json`; that match
does not attest the bytes currently flashed. The operator must connect it to the
existing deployment evidence and live firmware identity before admission.

## Exact count decoding

The archived v4 source calls RAW_ANGLE `encUpdate()` each control tick, gates
healthy state on the successful transaction plus configuration/magnet health,
and assigns unfiltered `encTheta()` to STATE `theta`. It sends float32 theta
using `%.7g`. The current sign is `ENC_INVERT=0`, and the live upright reference
must remain 370. Decode only this explicit source field:

```python
scaled = state.theta * 4096 / (2 * pi)
delta = round(scaled)
assert abs(scaled - delta) <= 0.001
raw_count = (370 + delta) % 4096
```

Also reject nonfinite theta and theta outside the audited wrapped interval
`[-pi-1e-6, pi+1e-6]`. The 0.001-count limit is a wire-format admission bound, not
a physical uncertainty claim. Compiling the actual archived encoder header and
using real C++ float32 arithmetic plus snprintf tested 24,576 cases: all 4,096
counts, three references (0, 370, 4095), and both signs. All roundtripped exactly.
The maximum integer residual for live reference 370/sign 0 was
0.0004406354476031993 counts. No count resampling or angle smoothing is involved.

Name the provenance **lossless raw-count decode from unfiltered STATE theta**.
Keep the original STATE payload/theta, source identity, unique board session and
tick, unwrapped board microseconds, host serial receipt, decoded count, and
format-audit hash. Distinct healthy ticks establish distinct successful register
reads under the audited firmware semantics; they do not establish independent
AS5600 ADC conversions. The board timestamp is control-tick start, before the I2C
read; host receipt must not replace it or be called exposure time.

INFO `encoder_raw_age_us` is time since the raw value changed, not time since a
successful transaction. Twenty-to-fifty INFO queries per second cannot prove
fresh independent measurements at a stable pose. Use INFO at capture boundaries
for configuration/reference/counter checks and as a stopped consistency check,
not as the native window sample clock. Repeated equal counts on distinct healthy
ticks are valid repeated observations; distinct counts are not a freshness gate.

## Admission and timestamps

Use only disabled, mode-0, fault-free, healthy states with calibration clear.
Require strictly increasing unwrapped tick and board acquisition time within one
board session, monotonic host receipts, and explicit duplicate handling. Preserve
all dropped/duplicate/invalid frame records; never pad missing samples. Reject a
window crossing a board restart, reference/configuration change, I2C error or
recovery-counter increase, or an unhealthy/calibrating/enabled state. Verify INFO
identity, reference 370, valid CONF and unchanged full readback before and after
each window. Define and record the permitted maximum packet gap before capture;
large gaps weaken evidence of continuous stability and must remain visible.

The existing fitter accepts only a scalar `sample_period_s`. A conservative
adapter can set it to the **minimum actual adjacent board-time spacing**, while
embedding every original timestamp and sample identity under dataset provenance
with `period_semantics="minimum observed spacing; not uniform sample period"`.
Then `(N-1)*sample_period_s` is a lower bound on actual elapsed time. Keep counts
unchanged and in acquisition order. The window must still satisfy at least 32
samples and a lower-bound duration of at least 0.4 seconds, span at most 4 counts,
and first/last-quarter drift at most 2 counts. If one short gap makes the duration
bound too small, acquire a longer window; never invent an evenly sampled trace.
A later versioned schema should accept actual timestamp arrays and validate
ordering/gaps directly, avoiding this conservative scalar compatibility bridge.

The real stopped stream capture already contains 4,124 unique healthy states,
with actual board gaps of 4–20 ms and maximum decode residual
0.00018684687302084058 counts. Its first 101 samples have actual duration 0.612 s;
the conservative 4 ms scalar gives 0.400 s. The current fitter accepts that
single window (span 1 count, drift 1 count). The source ledger is embedded in the
audit JSON. This is a compatibility diagnostic, not a paired calibration dataset.

## Independent pairs and physical reference

Collect fresh upright and hanging windows for every pair; reuse no upright
window, prior mean, or inferred pose. Preassign eight training pairs across two
independent acquisition sessions (two positive and two negative pairs per
session), then four held-out pairs across two new sessions (one per direction
per session). Session independence includes independent physical placement and
handling, not simply changing a string or reopening software. Preserve failed
windows and all approach history. Approach both poses in the pair in the same
verified raw-count direction; significant reversals or ambiguous settling require
an explicit new acquisition, not relabeling. Record approach traces so history
shifts and hysteresis remain testable.

The upright physical reference and fixture revision need an independently
established angular uncertainty bound. Convert that bound with
`uncertainty_degrees * 4096 / 360`. Encoder stability, camera fit scatter, and the
existing upright count cannot establish their own physical reference error.
If metrology or pose certainty is missing, retain the raw ledger with uncertainty
unknown and do not manufacture a numeric `reference_uncertainty_counts` to make
an eligible pair. Camera geometry can corroborate poses but needs its own physical
frame, distortion/perspective and uncertainty evidence before serving as metrology.
Fit training data once, then evaluate untouched held-out sessions; no approval or
reference write follows automatically. Direction/session disagreement may reject
the scalar model, which is a useful result given the observed history shift.

## Single owner and continuous observation

Use one bounded acquisition process as the only Rig/serial owner. Keep its
accepted-state logger and existing nonblocking UDP 3096 mirror active. The camera
service remains independent and always on. Run one persistent read-only SDK
shadow stream over the camera service; record native, aligned and fused traces
with source timestamps. Acquire window annotations and INFO on the owner's
serialized command path while stopped, not through a second console/serial
connection. INFO at boundaries avoids unnecessary register/serial work at
20–50 Hz. Preserve the chosen telemetry rate and record any change.

Shadow mapping validity is bounded (currently 60 s in the example evidence).
Long measurement sessions need explicitly renewed shadow sessions/configurations
or a separately verified longer mapping; never silently extend or reanchor an
expired map. Native board-timestamp capture can continue independently of shadow
validity. Stop/close the owner cleanly on cancellation and let the viewer mark
feeds stale. An unattended owner must not provide automatic arm, motion, or
reference-changing commands; those remain explicit operator actions.

Reproduce the local audit (no devices):

```sh
.venv/bin/python evidence/phase3/retuning-20261015/calibration/state-raw-decode-audit.py \
  --release /tmp/cartpole-retune-20261015/rehome-release.tar.gz \
  --capture evidence/phase4/vision-service-20261015/live-shadow-stream-capture.jsonl.gz \
  --output /tmp/state-raw-decode-audit.json
```
