The final reference 450 logs confirm a full native BAL interval and two native AUTO captures. This is consistent with the user's confirmation that correcting upright calibration restored native AUTO/BAL. The earlier reference 553 failure is therefore not evidence that the native controller remains unstable under the corrected calibration. This comparison is descriptive: pose, handling, and calibration changed together, so it does not independently isolate every cause of the earlier failure.

| Trial | First balance | Continuous balance | Raw-angle RMS in balance | Counted x range in balance | End |
|---|---:|---:|---:|---:|---|
| Ref 450 AUTO 10 s, initially upright/offcenter | 0.756 s | 9.244 s | 1.568° | −0.1192…+0.1573 m | Duration return at 10.000 s; disabled 12.868 s, fault 0 |
| Ref 450 AUTO 55 s requested, initially hanging | 1.408 s | 10.848 s | 1.966° | −0.0251…+0.2136 m | Recorded STOP at 12.256 s, fault 0 |
| Ref 450 BAL 10 s, initially upright/centered | 0 s | **10.000 s** | **1.663°** | **−0.0113…+0.1397 m** | Expected duration stop at 10.000 s, fault 3 |
| Ref 553 failed agent BAL 10 s | 0 s | 0.656 s | 19.674° | -0.1280…+0.1364 m | Angle release at 0.656 s; disabled 2.688 s, fault 0 |

All 2500 active samples of final BAL are balance mode 3/fault 0. Its angle range is −3.340…+2.021°; counted x RMS is 0.06771 m. The sampled active span is 9.996 s because the next 4 ms sample is the disabled duration-stop state. The native BAL MODE command is at Jetson monotonic 714517.263769660 s. The AUTO 55 s request was explicitly stopped early; this is not a demonstrated 55-second hold. Neither corrected AUTO nor BAL has a rail-braking sample while in balance.

| Native BAL startup metric | Failed ref 553 | Final ref 450 |
|---|---:|---:|
| Raw angle span, first 40 ms | 4.65820° | **0.35156°** |
| Raw angle RMS, first 40 ms | 2.36865° | **0.13329°** |
| Raw angle span, first 100 ms | 6.06445° | **0.43945°** |
| Raw angle RMS, first 100 ms | 2.47334° | **0.11922°** |
| Governed acceleration RMS, first 40 ms | 2.19799 m/s² | **0.08996 m/s²** |
| Governed acceleration RMS, first 100 ms | 3.49432 m/s² | **0.12848 m/s²** |
| MCU observer rate RMS, first 40 ms | 0.62021 rad/s | **0.01395 rad/s** |
| Counted x range, first 100 ms | −13.3875…0 mm | **−0.1500…0 mm** |

Windows are half-open board-time intervals from the first enabled telemetry: [0,40 ms) and [0,100 ms), containing 10 and 25 samples at 250 Hz. The first second of ref 450 BAL remains quiet (raw-angle RMS 0.09268°, range −0.26367…+0.17578°); larger cart excursions and angle variation occur later. See `startup-comparison.png` for the first 200 ms overlay.

The successful ref 450 hanging AUTO still has 5.27345° raw-angle span in its first 40 ms (6.59182° in 100 ms), then captures at 1.408 s. It starts near 174° with commanded motion, unlike upright BAL. A startup encoder wiggle alone is therefore not a deterministic failure test. This snapshot has no synchronized camera data; it cannot resolve physical angle versus sensor behavior during those fast variations.

The latest INFO before all three final trials has saved upright raw 450, home epoch 36, measured span 16511 steps, rail half-length 0.309075 m, encoder CONF 768 valid, and I2C counter 17. The recorded final upright calibration command is at 714459.210135738 s; subsequent INFO confirms 450. The previous agent BAL INFO has reference 553, epoch 34, span 16510, rail half-length 0.309075 m, and I2C 15. Reference count differences are calibration identities, not an independently measured physical zero error.

The final manual session's 41 latest parameter readbacks retain bw 10, leff 0.123999998 m, pw 3, pz 0.850000024, bal_pw 4.5, pc1 −5, pc2 −6, jmax 150, and the same remaining control settings. Those readbacks precede a HOME, so the earlier rail parameter 0.309037507 m should not replace later INFO geometry. No gain change is recorded between these final trials. The preceding `parameter-summary.md` and `parameters.json` document the agent baseline settings; calibration, rather than an algebraic gain change, is the correction reported by the user.

Counted x, commanded velocity, and governed acceleration are internal actuator quantities, not independent physical cart measurements. Mode 3 occupancy alone is also not a balance-quality metric; angle and position metrics accompany every duration here. These results establish the observed bounded native holds, not long-term reliability or learned-policy performance. No hardware, network, training, or production edits were used for this audit.

Reproduce from the repository root into a new output directory:

```sh
python3 evidence/policy-recovery-20261021/transfer-audit/audit_reference450.py --snapshot evidence/policy-recovery-20261021/transfer-audit/reference450-native/source-prefix.jsonl.gz --output /tmp/reference450-audit-reproduction
```

`analysis.json` includes exact source/script/output identities, all transitions and control commands, complete parameter/INFO snapshots, first 100 ms state values, and window metrics. `traces.json` retains the selected active samples. The preserved compressed source has SHA256 07523dac1391130656f41d53e994ffce4893851f24b127628272a5252f17692b; decompressed SHA256 39442b6753c8dd9360cf7272fed2deff7ef51defd4f201b3e82a0abe58868eb7 (69,954,645 bytes, 175,486 records). The failed agent BAL raw source SHA256 is 3c697798eab2bef55ac2d9fc72b4d30bdd8ca7a907a021d9658fed75721a57e1. Earlier snapshots were preserved unchanged.
