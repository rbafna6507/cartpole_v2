# Integrated vertical axes implementation plan

**Goal:** User-confirmed left raw + DOWN/right raw + UP, integrated cartpole firmware and console: home, stop, independent/paired physical up/down moves, counted bottom reference, status, finite paired sine.

**Architecture:** Preserve cart's 7 us pulse generator and controller math. Add independent 4 us bounded Z generator with shared D8 enable and existing safety precedence. V2 framing/session/heartbeat remain authoritative. Use a Z-only executor mode 15 when cart is idle; never silently arm cart from Z commands. Encoder/cart limit/global STOP/host loss must inhibit all motion. User confirms rails supported on disable, rated bottom stops, 200 mm travel,5 mm lead,defaultBED16microsteps; assume200steps/rev as existing commissioning.

## Wire contract
- Firmware identity `executor-v7-vertical`; same cart parameter and learned-policy compatibility as v6, explicitly supported by SDK (do not change old constant semantics silently).
- `V2 ZSTATUS sid` -> `V2 Z sid phase refs left_mm right_mm bottom_mask` (8 tokens; phase0idle1move2bottom3transfer4sine; masks0..3).
- `V2 ZREF sid left|right|both`: stopped, explicit operator bottom assertion for selected axes; zero selected count. No sensor claim.
- `V2 ZHOME sid left|right|both`: stopped-only, selected DOWN40mm/s5s, no stall/contact sensing; completion marks bottom_mask but does NOT automatically establish reference.
- `V2 ZMOVE sid left|right|both signed_mm speed_mm_s`: physical +UP/-DOWN; selected reference required; <=20mm per command; default2mm/s fromconsole, firmware max40; quintic ramps and endpoint0..200mm checks.
- `V2 ZSINE sid amplitude_mm hz center_mm seconds`: default20,1,25,10; paired, refs required, near-level starting pose,profiletravel/pulse bounds and ramps as commissioning. May start alongside active cart exceptHOME/REHOME/recovery; existing cart authority must remain unchanged.
- `V2 ZSTOP sid`: cancel bothZ axes; leave activecart authority intact; stop standaloneZ anddisable when no cart. GlobalSTOP always allaxes.
- Mutations return normal `V2 OK sid COMMAND`; rejection normalERR. Metadata separate Z frame does not modify existing S-frame shape. Query may run during motion and is logged bySDK.
- On cancel/fault invalidate affected activeZ references. Normal completed boundedmoves retain reference; idle globalSTOP may preserve stationary countedreference because supportmechanics confirmed. NewHELLO invalidates references. No automatic motion after restart/reconnect/faultclear.

## Tasks
- [x] Firmware: state/profile and protocol tests first; separate pulse timer, physical polarities, sharedsafety, isolated authority, boundedstop,reference lifecycle; nativewhole-sketch +Teensycompile.
- [x] SDK/console: strictZmetadata parser, asynchronous methods with hostfreshness/deadline tracking for standaloneZ, normalcart concurrency preserved; console `z status`, `z reference AXIS`, `z home AXIS`, `z move AXIS up|down MM [SPEED]`, `z stop`, `z sine [A HZ CENTER SEC]`; tests and v7compatibility.
- [ ] Integrate/review: entire existingexecutor/rig/console tests, check learnedpolicy firmware identity handling and no oldsourcehash alteration, stage separate runnable release +compiledHEX without flash/motion until requested handoff; docs andcommit/push.

## Critical checks
Malformed/nonfinite/oversize motions; opposite motorpolarities; reference invalidation; hardstop timedNOTsensorverified; sharedenable; originalcart timer unchanged; globalfaultwhileZactive; independentZstopwhilecartactive; no Zpulseswithoutfreshauthority; nativeSDK completion and hostdeadlines; oldfirmware rejects unsupportedcommands beforemotion; no duplicate serialowners.
