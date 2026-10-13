# Frequency-test poor-motion review

Source: `logs/frequency_test/frequency_20260915_203801_245784.csv` and its event sidecar.

## Observed commands

- 100 mm peak-to-peak, 0.25 Hz: startup ramp 8 s; total active time about 21.79 s including an 8 s finish ramp. Peak requested speed 0.07854 m/s (~39.27 RPM), acceleration 0.12552 m/s² including ramps. Peak pulse-inferred position error versus reference 0.0805 mm. Telemetry spacing 19–21 ms. The user reports poor physical motion even after ramp-up.
- 100 mm peak-to-peak, 0.05 Hz: old startup ramp 40 s; stopped after 18.75 s, never reached full amplitude. Commanded rate at 1/2/5 s was approximately 0.24/1.71/11.98 microsteps/s. This explains isolated early movements in this run, but not the bad full-amplitude 0.25 Hz response.
- Logs measure software commands and generated pulse counts, not motor movement, pulse voltages, or driver current. Telemetry frequency is not waveform update frequency. V1 did not record maximum update or ISR gaps.

## Hardware confirmed by user

SparkFun Big Easy Driver, 24 V motor supply; MS1/MS2/MS3 unconnected; 3.3 V solder jumper bridged; ESP32/driver grounds connected. Motor current limit has not been adjusted as far as the user knows. Motor rated phase current and measured TP1/VREF remain unknown.

The board's pull-ups select 1/16 microsteps with MS pins unconnected. The confirmed 3.3 V jumper removes the potential 5 V logic-supply / 3.3 V input-threshold mismatch. Do not change those settings based on this review. An unsuitable current limit, coil connection issue, or pulse timing/electrical issue remains possible; none is proven by the existing logs.

Primary references: [SparkFun Big Easy Driver](https://learn.sparkfun.com/tutorials/big-easy-driver-hookup-guide/hardware-overview), [Allegro A4988 datasheet](https://www.allegromicro.com/-/media/files/datasheets/a4988-datasheet.pdf).

## Applied diagnostic revision

V2 decouples ramp duration from oscillation period, defaults to 2 s, and accepts 0.5–30 s in the GUI. Waveform derivatives and speed-bound validation use the chosen ramp. The dedicated firmware still uses STEP/DIR on GPIO25/26, a nominal 125 kHz DDS timer, and ~1 kHz waveform updates; it does not receive individual motion samples from the GUI.

A once-per-second D record measures update count and maximum update gap, timer count and maximum timer gap, generated pulse count, and CPU-timestamp estimates of minimum GPIO pulse high/low times. The GUI displays and logs these. They do not verify the electrical waveform at the driver or physical cart tracking. A4988 minimum STEP high and low times are both 1 µs.

Tests: waveform range/derivatives/ramp/limits; five host tests including serial handshake, stop preemption and heartbeat loss; browser tests for preview, invalid travel, Run, Finish, Stop, and responsive layout; ESP32 build passed (304159 program bytes, 21096 global bytes). No automatic motion test was performed. Physical tracking remains unresolved.
