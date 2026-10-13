# Next identification trials

This is a planned experiment for the sole parent hardware operator. No motion was
commanded by this assessment. Preserve EEPROM reference 3485 and the proven
original controller build. Execute forced trials after the bounded executor and
stopping have been commissioned, with the cart physically centered.

1. **Establish angle zero and timing.** Record 10 seconds of an independently
   verified hanging, stationary pole before and after each trial. Save raw
   encoder/reference, theta, board time, motor enable state and health, with an
   image/video of hanging geometry. Current equilibrium near 3.03 rad is about
   -0.11 rad from pi. Any offline offset must come from that physical reference,
   remain explicit in provenance and preserve raw data; the dynamic nuisance fit
   is not a calibration correction. Establish explicit clock mappings before
   joining camera, board and host sources.

2. **Separate passive and forced dynamics.** Obtain two independent 20–30-second
   free decays at different small initial amplitudes, with cart location and
   motor enable state fixed. Independently verify real pendulum motion against
   magnetic noise/vibration. Passive data can constrain length/damping, but cannot
   identify input gain/delay.

3. **Collect predetermined forced and held-out runs.** A starting displacement
   design is `x_ref(t)=sum(A_i*sin(2*pi*f_i*t+phase_i))`. Use two 20-second training
   runs with 0.5 mm per component at 0.8, 1.3 and 2.1 Hz. Away from ramps, summed
   displacement/velocity/acceleration bounds are 1.5 mm, 0.0132 m/s and 0.133 m/s².
   Use two separate held-out runs with predetermined phases and 0.4 mm per
   component at 0.7, 1.6 and 2.3 Hz: bounds are 1.2 mm, 0.0116 m/s and 0.132 m/s².
   Include smooth 2-second start/end ramps; their derivatives must also fit the
   already commissioned travel, velocity, acceleration and jerk limits. These
   waveform values are proposed signals, not commissioned hardware bounds.
   Verify a short reduced-amplitude trial first. Frequency coverage and distinct
   initial conditions help distinguish gravity, damping, gain and delay.

4. **Record applied input and independent cart measurement.** Save desired and
   accepted/applied acceleration plus board application timestamps at 100 Hz or
   faster, including gaps, calibration resets and health failures. Use calibrated
   metric cart measurements to identify physical cart response/slip. If those are
   unavailable, preserve `acceleration_kind=commanded` and describe gain/delay as
   composite effective parameters. Step counts remain travel proxies. Omit omega
   when its derivative effective time is unknown; never differentiate/interpolate
   across a gap.

5. **Preserve independent acceptance.** Set priors and thresholds before examining
   held-out results. Require actual angular span >=0.15 rad, input standard
   deviation >=0.05 m/s², at least 20 valid training windows, identifiable zero
   diagnostics, physical parameter bounds and held-out prediction/residual checks.
   Increase duration or excitation only within commissioned bounds if response is
   inadequate. Reject failed trials without retrospectively loosening thresholds.

The successful original-controller swing-up/balance run supplies controller
acceptance evidence, but its rejected fit cannot supply an identified model.
Nuisance gravity/input offsets (-0.0084/+0.4142 rad) disagree. Planned measurements
must distinguish commanded-versus-achieved acceleration, timing, angle calibration,
flexible motion and model mismatch; a single inferred zero correction is insufficient.
