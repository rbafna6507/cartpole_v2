The preserved logs show **no change in the algebraic AUTO/BAL feedback gains**. Compared with the latest sustained native AUTO validation success on October 20, **39 of 41 controller settings match exactly**. The two differences are observer bandwidth (`bw` 8→10 Hz) and the tiny home-derived rail change. The saved encoder reference is a separate, materially different calibration identity: 330 in the historical success, 553 in the agent native trials.

| Preserved state | Sustained native AUTO validation, Oct20 | Current native AUTO | Current native BAL / user's old-console snapshot |
|---|---:|---:|---:|
| Saved upright raw count | 330 | 553 | 553 |
| `bw` | 8 | 10 | 10 |
| `leff` (controller) | 0.123999998 m | identical | identical |
| `pw`, `pz` | 3, 0.850000024 | identical | identical |
| `bal_pw`, `pc1`, `pc2` | 4.5, −5, −6 | identical | identical |
| `jmax` | 150 | identical | identical |
| Rail parameter | 0.309000015 m | 0.309037507 m | 0.309074998 m |
| Home epoch / measured span | 17 / 16506 steps | 33 / 16509 | 34 / 16510 |
| Encoder CONF | 768, valid | identical | identical |
| Recorded I2C error counter | 5 | 13 before trial | 15 before trial |

All other speed/acceleration, swing, capture, release, rail-margin, and return settings also match exactly. The rail difference is about 0.0375 mm for current AUTO and 0.0750 mm for BAL. The model's 0.160304 m effective length belongs to the simulator; it did not replace the controller's 0.124 m `leff`.

The historical success is `coupled-validation-01`, session 791176552, in the preserved `id-followup-20261020.tar.gz`: two native AUTO trials each held balance for approximately 22.49 s of 25 s. Its complete parameter readbacks before both MODE commands match its report. The raw log digest also matches the pre-existing native-validation analysis. Current values come from all 41 wire readbacks in `inspect-01` (77.69 s before native AUTO) and `upright-before-native-bal` (24.62 s before native BAL), consistent with their JSON reports. The native trials themselves have no parameter queries or writes. The completed user old-console snapshot has all 41 readbacks identical to current pre-BAL, including bw10 and reference553. No live access was performed; actions outside these preserved files cannot be excluded.

An apparent historical contradiction is resolved by command chronology: the later `native-baseline-bw8-25s-01` report stores **pretrial bw10**, then explicitly sets **bw8 before MODE**, and restores10 afterward. Its saved reference was294. It completed the requested operation but did **not** sustain balance: its longest balance-mode interval was about 2.024 s, with repeated rail recoveries. It is not the latest sustained success. Generic analyzer output that lists that report's pretrial bw10 must not be read as the active-trial setting.

`bw` changes the angle/rate observer's phase/noise response, even though it leaves algebraic gains unchanged. Native BAL also intentionally chooses the separate `bal_pw=4.5` gains; AUTO's captured balance uses `pw=3`. Reference330→553 changes decoded zero for a fixed raw count, but counts alone cannot tell whether physical vertical changed: magnet/installation and calibration epochs may also differ. This audit neither demonstrates a 19.6° physical zero error nor establishes bandwidth/calibration as the cause of the current failures. The quiet zero-demand hanging result also means the startup encoder transient is not universal at every enabled pose.

Complete exact dictionaries, per-field differences, wire MODE snapshots, calibration identities, archive/member hashes, source script hash, and uncertainty are in `parameters.json`. Reproduce with `audit_parameters.py --user-snapshot /tmp/user-console-old-snapshot.jsonl --output NEW_JSON`.

The later completed user-console prefix adds two explicit upright calibrations: 553→551, then 551→1135. The second shift is 584 counts (51.328° for an unchanged raw sensor coordinate), but whether the user held the same physical pose is unconfirmed. It must not be called drift or a correct new vertical. All 41 recorded control settings still match the agent pre-AUTO readback exactly; no gain change appears in this prefix (`parameters-new-manual-prefix.json`). These later references supersede 553 only within that recorded manual session, not the earlier baseline trials.

After the first calibration to 551, the user issued `auto 10000` from upright. It entered native balance mode immediately and remained there 9.996 s (2500 samples), then performed duration return. Encoder angle was −7.03…+16.35°, RMS 2.49°; counted x −0.0248…+0.2393 m, fault 0. No independent record establishes whether the pole was held or released. This is useful evidence that the present native controller can remain in balance mode, not proof of hands-free reliability or that calibration alone caused the improvement (`manual-upright-auto-10s.json`).
