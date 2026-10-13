# Control timing, language, and Jetson–Teensy transport

The Phase 0 design assessment below is retained as historical context. The new
executor now supports 100/250/500/1000 Hz USB telemetry and bounded external
acceleration. Current measured results appear in the final section; these short
checks do not establish hard real-time host control.

## Phase 0 design assessment (2026-10-13)

## Can 100 Hz be increased?

Yes. The existing sketch explicitly clamps `rate` to 100 Hz, and the console
validates/clamps it too. It is a software ceiling, not a demonstrated USB limit.
The controller and estimator run at 1000 Hz, while the step timer runs every 7 us.
The present protocol mainly selects onboard control modes or manual velocity;
it does not yet provide the bounded external acceleration interface needed for v2.

A useful first v2 target is to benchmark 250 and 500 Hz state/action exchange,
with 100 Hz and 1000 Hz as comparison points. Choose the lowest rate that meets
measured stability and robustness needs. Do not simply raise the telemetry clamp:
check formatting cost, transport backpressure, driver buffering, clock alignment,
sample loss, host scheduling, and completed MCU deadlines under concurrent load.
Fast binary state frames may help, but must earn their complexity against a
measured compact framed alternative.

| Rate | Period | Interpretation |
|---|---|---|
| 80 Hz | 12.5 ms | Camera request; not necessarily valid observations per second |
| 100 Hz | 10 ms | Current telemetry ceiling |
| 250 Hz | 4 ms | Candidate host control period |
| 500 Hz | 2 ms | Candidate host control period |
| 1000 Hz | 1 ms | Current onboard estimator/control period |

100 Hz can be adequate for some cartpole controllers, but this rig's successful
1 kHz controller is not evidence that an unchanged 100 Hz port will behave the
same. Sampling, stale inputs and transport delay alter its closed-loop behavior.
The actual controller uses filtered `th_hat`; current telemetry publishes raw
`th` and filtered `thd`. A faithful baseline needs the same estimator state or an
explicitly validated host estimator. Repeating a 100 Hz measurement in a 500 Hz
loop does not create five fresh observations.

Measure sensor-to-action age, p50/p95/p99/max scheduling delay, consecutive missed
deadlines, MCU deadline misses, and behavior on overload/disconnect. Repeat with
vision, video encoding, recording and policy inference active. Observation age and
action expiry must be visible on the MCU; health pings cannot renew old actions.
Vision angle and velocity have different effective timestamps (the usual velocity
fit already adds about 25 ms of effective delay at 80 FPS before other pipeline
delays). They cannot be presented as a simultaneously fresh state without an
explicit estimator and uncertainty.

## Python and alternatives

| Option | Strength | Limitation and proposed use |
|---|---|---|
| Python policy and runner | Accessible, direct MuJoCo/Gymnasium integration, easy experimentation | Interpreter/allocation/Linux scheduling jitter; benchmark first for bounded small policies |
| Python API with a C++ or Rust broker/runner | Keeps accessible policy/simulation APIs while moving transport, scheduling and inference orchestration to a tighter implementation | More build/interface work; still not hard real time merely because it is native code |
| Compiled model inference behind the same SDK | Predictable supported model interface and resource accounting | Model format restrictions and measured inference deadlines still required |
| Inner feedback controller on Teensy, slower host supervisory policy | Retains the proven high-rate local loop | Changes the action semantics and limits arbitrary host feedback policies; useful as a separate explicit mode |

Recommended: keep the public API in Python, preserve the local 1 kHz motion
executor, and start with a small measured host loop. Move only demonstrated
bottlenecks into native code. A native runner or real-time Linux configuration
does not replace the independent MCU deadline and motion limits. Internet,
dashboard rendering and video delivery never participate in feedback timing.

## USB versus Ethernet

Teensy 4.1 exposes native USB device communication at up to 480 Mbit/s and native
10/100 Mbit Ethernet. USB serial ignores the configured UART-style baud rate;
115200 is not a throughput cap here. These are bus capabilities, not application
latency measurements. [PJRC USB serial](https://www.pjrc.com/teensy/td_serial.html),
[Teensy 4.1 specifications](https://www.pjrc.com/store/teensy41.html).

For illustration, a 100-byte state at 1000 Hz is only 100 kB/s of payload. Both
links have sufficient nominal bandwidth for such messages. Tail latency, stale
queue handling, independence from camera traffic and disconnect behavior matter
more than raw link speed.

| Link | Advantages | Costs |
|---|---|---|
| Direct USB CDC | Already working; no IP setup; stable device ID; existing upload route | USB topology/host scheduling can introduce jitter; sharing a hub is a variable to measure |
| Dedicated Ethernet TCP | Existing firmware/console support; separates camera USB traffic; conventional socket tools | IP setup, stack/buffering cost, ordered retransmission can delay newer commands behind old data |
| Dedicated Ethernet UDP | Preserves packet boundaries; can select only the latest state/action | New protocol work for loss, duplicates, ordering, ownership, integrity and explicit expiry; no automatic safety advantage |

The saved Ethernet firmware uses `192.168.50.2:9000`; the dedicated peer is
`192.168.50.1/24`, without a gateway. Its existing application protocol has no
internet authentication. It belongs on the private rig link only.

QNEthernet documents TCP retry/close delays and exposes nonblocking operation and
link/connection controls; application deadlines cannot rely solely on TCP
disconnect notification. [QNEthernet documentation](https://github.com/ssilverman/QNEthernet).

Recommendation: retain USB as the baseline and benchmark it against the existing
private Ethernet TCP path before choosing v2's primary transport. Prefer a
dedicated Jetson USB port for that comparison, keeping the camera on its USB3
path. Ethernet may win on isolation or latency consistency; it is not inherently
faster for these tiny commands. Consider UDP only if measured stale-queue behavior
justifies it. Both transports should implement the same action/session/deadline
contract, and changing one must not change policy semantics.

Limit switches are not yet implemented. Add them to the future Teensy safety
executor and commission stopping behavior separately; increasing telemetry rate
does not establish physical containment.

## Later live executor measurements (2026-10-13)

The new executor removes the archived 100 Hz ceiling. With vision running and the
motor supply off, two-second stopped measurements delivered all board snapshots
at 100/250/500/1000 Hz with zero new MCU deadline misses or active-reader drops.
The serial adapter now drains available bytes rather than waiting for a 512-byte
buffer to fill. At 250 Hz its host-arrival median was 3.99 ms, p99 7.28 ms, max 9.08 ms;
at 1000 Hz median 0.933 ms, p99 4.18 ms, max 7.00 ms. These intervals include host scheduling
and parser effects; they are not sensor-to-action latency or hard real-time bounds.
The before/after records are under `evidence/phase3`.

A live 250 Hz zero-command loop and 20 ms action-expiry test passed. The preserved
onboard 1 kHz controller also completed a 10 s SDK-commanded swing-up/balance trial.
Neither establishes full host-controller stability at 250 Hz. USB remains the
implemented new transport; the archived Ethernet path was not benchmarked or
ported into the new executor in this phase.
