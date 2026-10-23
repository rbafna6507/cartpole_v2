# Operator release — October 23, 2026

The user's follow-up requested completion of the GUI, a complete command cheat sheet, one-command operator startup, repeatable additive deployment, and staging the 1,024,000-step projected-PPO candidate.

- The user reported physical swing-up success with the unchanged 102,400-step rail1mm actor. `policies/working.json` is its exact copy; `policies/1m.json` is the new development candidate.
- Both native Mac viewer modes were freshly inspected through the GUI: rendering, reset and pause worked. Headless parity and regression tests cover authoritative simulation stepping; display interaction cannot edit physical simulation state.
- The million-step receipt, ZIP CRC, timestep and actor/model hashes matched before export. See `million-policy/sdk-parity/report.json`, both `nominal-*/report.json`, the retained `export-protocol.json`, and the candidate's `recovery-manifest.json`.
- Both evaluation backends held all four nominal hanging and all four upright starts with no faults. All hanging runs used rail braking. This does not establish million-step hardware quality or superiority over the working policy.
- Both PPO and retained smoke training completed 128 steps, checkpoint roundtrip and final SDK emission parity. `training-smoke-summary.json` points to local raw run records.
- Independent code review found an activation-order failure path. Collision and write-failure tests reproduced it; activation now follows successful launcher installation. Offline release verification explicitly loads the NumPy backend as well. Relative custom `--uv`/`--python` paths remain a documented limitation; use absolute paths (or a bare Python version selector).
- No serial, firmware, physical motion, calibration, camera restart or new cloud training was performed.

The complete source/doc changes are on `codex/live-rig-platform`. `COMMAND_CHEATSHEET.md` gives launch, training, viewer and deployment commands. `COMMAND_REFERENCE.md` captures 105 real help outputs. The release manifest and Jetson installation verification record identify the installed bytes separately from subsequent documentation-only commits.
