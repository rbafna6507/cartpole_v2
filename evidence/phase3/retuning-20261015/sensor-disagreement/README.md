# Sensing investigation, 15 October 2026

The active physical board remains executor-v4-rehome with the directly measured
upright reference 370. All motion tests below ended stopped at the established
home. These are experimental trials, not accepted control tuning.

- Twelve corrected-reference length/bandwidth trials and six cart-gain trials
  failed to reach two seconds of continuous balance. Larger effective length
  failed to capture; stronger cart gains increased saturation without a reliable
  improvement. No winning profile was promoted.
- Direct upright repeated near raw371 with the camera seeing near vertical.
  Hanging was about10 degrees from the ideal half-turn conversion. During the
  slow manual sweep, angle-dependent residual reached about16 degrees; only one
  direction had full-turn coverage. Similar visible hanging poses differed by
  about2.8 degrees between observations. A constant correction is not validated.
- The disabled/zero-command-enabled/disabled test produced only0.01 degrees
  encoder mean change and0.06 degrees camera change, with no measured cart
  displacement. This condition did not reproduce a motor-enable electrical bias.
- Camera and counted cart displacement correlate above0.999 in the compared
  motion runs. The cart's drift toward the right is real.

`visible-upright-report.json` retains simultaneous source readings and full camera
calibration for an explicit shadow-fusion anchor. Raw marker geometry and the
portal's calibrated theta are different coordinates; do not interchange them.
`manual-angle-map-compact.json.gz` retains the recorded sweep. The offline static
fit is diagnostic only and has not transferred to dynamic control. The calibration
directory next to this one intentionally contains an unapproved insufficient-data
model. No113-count correction or nonlinear angle map has been installed.

The manifest hashes these copies. Some analysis scripts retain their original
temporary input paths; their saved outputs are included. Remote raw runs remain
under `/home/rbafna/cartpole-v2-runs/retune-20261015/`.
