# October 20 live characterization and simulation evidence

Operator entry point and current limitations: [checkpoint](../../docs/checkpoint-20261020.md).
No artifact in this directory grants hardware acceptance.

- `live/`: sealed successful **and failed** real campaigns, initial/working/homed/final readbacks, and both motor-disabled numeric actor probes. Archives preserve raw logs and campaign manifests. No usable camera measurements were collected this session.
- [Final timing review](timing-gc-comparison-v3/README.md): measured GC failure and mitigation, subsequent unresolved host dispatch failures, and next diagnostic boundaries. Earlier timing versions preserve investigation history.
- [Driven-model report](driven-combined-v1/report.md): fixed-ODE training/validation predictions and plots, including explicit post-hoc sign/lag and shorter-horizon checks. Raw MCU commanded acceleration is a conditional input, not independent physical cart truth. No new physics fit promoted.
- [Learning evidence](learning/README.md): six training trials, initial/final paired heldout runs, ordinary numeric SDK export, stress, and the separate teacher-gain diagnostic. Full recipes/checkpoints/traces are in the verified compressed archive.
- `tools/`: reusable read-only analysis, GC diagnostic collector launcher, and stopped-only actor timing probe. The probe never arms or commands acceleration.
- `pytest-full.log`: 1,717 passing tests, 7 skips, 456 passing subtests after the source changes. Probe scripts were subsequently exercised on actual stopped hardware.

The candidate remains `training/candidates/balance-20261020/actor.json`, with
`hardware_accepted=false`. The frozen simulation profile is
`training/profiles/rl-encoder-20261020/`. Neither is a claim of robust transfer.
