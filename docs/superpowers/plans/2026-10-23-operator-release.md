# Operator release and viewer completion implementation plan

> Implement inline using the existing feature branch. Preserve old deployments and baseline artifacts.

**Goal:** Finish the local viewer, provide one-command operator launch and repeatable additive releases, stage the projected PPO 1,024,000-step actor, and document all operator/training/viewer commands.

**Architecture:** Keep existing firmware/control/inference contracts. A standard-library launcher composes the tested CPU supervisor and GIL-scoped console with defaults and optional overrides. A release installer copies a committed bundle to a new directory, verifies hashes and offline imports/actors, then atomically selects an `active` symlink. Explicit policy aliases distinguish user-tested `working` from untested `1m`. Existing `current` remains historical.

**Scope:** User requests 0.25 through 2 on 2026-10-23 are the specification and authorization. Portal design is next, with joint decisions; no public portal execution now. No motion, serial access, firmware flash, camera restart, or alteration of old releases.

## Tasks
- [x] Finish viewer packaging: installed `cartpole-view-policy` entry point, verify learned/reference headless and GUI behavior, document controls and all flags.
- [x] Test then implement operator launcher: default device, 250 Hz, preserve board tuning, 1 ms GIL wrapper, CPU camera 0-3/control 4-5, realtime child priority 10. Only raise the launching process's realtime limit using sudo prlimit when required; never execute the console as root. Help and dry-run perform no sudo, serial, or affinity mutation. Explicit overrides remain available.
- [x] Verify original checkpoint receipt/ZIP, export 1,024,000-step PPO actor, evaluate SDK/SB3/numeric parity and nominal rollouts, save provenance and stage as unaccepted candidate. Preserve working 102,400-step actor bytes and identity.
- [ ] Add repeatable immutable release packaging/install/selection and stable PATH launcher; fail safely on existing target or invalid bundle. Verify offline on Jetson; retain old release and explicit rollback.
- [ ] Add comprehensive command cheat sheet, update README with commands and dated user-reported hardware success; commit and push. Finish the independently running preservation archive.

## Review focus
- Help/dry-run must work with no serial device and never request privilege.
- Explicit console flags override defaults, including startup profile versus keep-board-params.
- Relative user paths must keep their meaning; PATH wrapper starts in selected release intentionally.
- Existing actor provenance and working policy must remain valid after packaging.
- Failed staging must not switch the active release or overwrite old content; no hardware startup during deployment.

## Validation
Targeted launcher/viewer/release tests first, full project pytest after implementation, real GUI smoke on macOS, real Jetson help/dry-run and numeric actor load (no hardware), GitHub branch identity verification. Record every limitation and deployment identity.

## Review record

Independent review: no critical findings. Activation-before-launcher failure was Important; reproduced collision/write failures, then fixed. NumPy validation gap was regraded Important because deployment must exercise its actual inference backend; a broken-backend test failed first, then passed after explicit verification was added. Relative custom executable paths were Minor and are documented as requiring absolute paths. Physical behavior is left to the user; GUI, checkpoint, runtime and installation acceptance are verified separately by the primary agent.
