2026-10-16 autonomous encoder-only tuning

Control: native Teensy 1 kHz AUTO/BAL. SDK supervises, sends heartbeat, records 250 Hz telemetry, and mirrors encoder telemetry to the persistent vision app. No vision/fused feedback was used. No firmware flash or reset occurred during this session.

Routine AUTO trial duration is now 25 seconds in native_trial_encoder.py. Other diagnostic defaults remain 8 seconds; the ordinary harness still rejects AUTO durations above 30 seconds. Separate fixed-profile 60-second harnesses were used for longer confirmation. Console defaults were not changed.

Best candidate: candidate-20261016-bw10.json. It contains 40 settings and omits measured rail geometry. Principal settings: bw=10, pw=3, pz=.85, pc1=-5, pc2=-6, leff=.124, ke=4, kpx=40, kdx=2, approach_v=.2, catch_a=.25, catch_r=3, catch_v=.3, jmax=150 m/s^3, vmax/vmax_s/vmax_b=1.5 m/s, amax_s/amax_b=25 m/s^2. All switch, watchdog, encoder and rail protections stayed enabled. Larger jerk225 and stronger energyke5 were comparisons, not the saved recommendation.

Reference: fresh human-resting-upright reference362 was captured earlier today. Experimental constant trims340 then330 were evaluated; the best candidate uses saved330 (minus32 counts = minus2.8125 degrees from362). This is NOT a validated encoder nonlinearity or hanging-to-upright model. Hanging was observed and stability-checked before each AUTO, without overwriting reference330. The tuning profile does not contain or automatically change this reference.

Interpretation: lower observer bandwidth reduced fast angular-rate feedback and the acceleration demand the jerk governor could not follow. This is consistent with the measured reduction in oscillation; the physical source of high-frequency motion/noise remains unproven. Raw encoder angle and commanded/step-derived cart position are not independent truth measurements. Mean balance angle alone is not a valid zero-calibration estimator.

Capture limitation: a missed initial catch can still lead to a swing-up loop. In ag6 the settled loop never entered the approach region: minimum |estimated angle|1.188rad, versus approach_angle=.8rad. Raising ke from4 to5 in ah1 did not rescue it and was reverted. After fresh physical homing, the restored candidate in ai1 again held to the25-second deadline. Finite holds ending at a scheduled deadline are right-censored, not proof of indefinite balance.

Diagnostics: ag5 captured at2.496s and balanced continuously for57.504s until the60-second deadline, with raw-angle RMS2.9047 degrees and no rail recovery. During its subsequent REHOME, a103ms delay between Python receive timestamp and recording triggered the100ms stale-telemetry guard. Board timestamps continued in4ms increments and buffered states drained afterward. This establishes a host processing/scheduling pause, not a missing board-telemetry generation interval. GC was not instrumented then and is not proven to be the cause. A separate guarded REHOME succeeded. ag6 used a smaller2048-record ring, deferred duplicate report conversion, and omitted observation-only camera SSE; encoder mirroring remained enabled. It saw no host-stale fault before an unrelated encoder fault terminated it; measuredGC max7.10ms. Those diagnostic optimizations are not a proven SDK latency fix.

Encoder fault: ag6 incremented cumulative I2C errors4->5 and fault4 disabled motion. The stopped encoder was observed healthy with clear switches for2seconds, unchanged error count and valid configuration, before normal CLEAR. Physical two-switch HOME then succeeded (epoch8, span16510 steps =619.125mm, rail_half309.075mm). Normal boundary is294.075mm; hard rail fault is299.075mm; host guard296.575mm. No health check was bypassed. Earlier this session one homing-latch fault was logged; one normal retry succeeded after stopped diagnostics.

Data suitability: useful for controller comparison and exploratory system identification. Not accepted as a qualified plant model; camera framing changed and upright tracking was often invalid, and cart position is counted motor steps. No MuJoCo physical parameters or encoder calibration model were promoted from these trials.

Reproduction on Jetson:
  cd ~/cartpole-v2-live/releases/platform-20261015-v6-tunable
  uv run --locked --extra hardware cartpole-console --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250
Then at cartpole>:
  load profiles/candidate-20261016-bw10.json
  info
  status
  auto 25
The profile does not home the rig or calibrate upright. Current saved reference330 is required to reproduce this exact comparison. After power-cycle or lost home, use normal physical HOME; do not blindly apply the raw330 count after mechanical encoder changes. No motor-powered firmware flashing.

Evidence: session-comparison.json uses full raw board JSONL timestamps. captures/ contains losslessly compressed full trial reports. Their SHA256 hashes and original Jetson paths are in manifest.json. Most full raw board logs remain on the Jetson at those paths; ag5 raw log is also copied here. Filtering-comparison shows the earlier BW30 t1 hold and BW10 ag5 hold, without implying they are randomized repetitions.

Final verification: all40 stored candidate parameters match live readback. Board stopped/disabled, x0, fault0, misses0, reference330, homeepoch8; cumulativeI2C5. In ag7, firstcapture2.526s, continuous observedbalance57.472s, angleRMS3.5258 degrees, max|x|0.2626m. It completed automaticREHOME and stopped at countedzero. GC callback max9.079ms, no stale-host fault, no recording overflow. This single successful low-allocation repeat does not establish that the prior latency issue is fixed.

Saved-candidate repetitions (same40parameters; reference330; freshHOME beforeai1/ag7):
Trial | duration | firstcapture | longesthold | end-to-end result
reference330-pw3-bw10-ag1 | 25s | 2.584s | 20.712s | passed
reference330-pw3-bw10-ag2 | 25s | 2.522s | 22.476s | passed
reference330-pw3-bw10-ag3 | 25s | 2.506s | 17.276s | passed
reference330-pw3-bw10-ag4long | 30s | 2.519s | 27.480s | passed
reference330-pw3-bw10-ag5confirm60 | 60s | 2.496s | 57.504s | interrupted; see notes
reference330-pw3-bw10-ag6confirm60-lowalloc | 60s | 1.995s | 0.172s | interrupted; see notes
reference330-bw10-home8-baseline-ai1 | 25s | 2.556s | 22.444s | passed
reference330-pw3-bw10-ag7confirm60-lowalloc | 60s | 2.526s | 57.472s | passed

Across8 saved-candidate attempts,7 were balancing at their planned AUTO deadline;2 of those requiredrecapture. The remainingattempt faileditsinitialcatch and later stopped onencoderfault. Of3 planned60s attempts,2 helduntil60s (onehadreturnhostpause),1 endedearlyonencoderfault. This isnotanunqualified7/8 whole-run success claim. There are58 completedAUTO experiments inthissession, includingfailedcomparisons.
