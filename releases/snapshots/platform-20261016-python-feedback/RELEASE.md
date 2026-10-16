# Experimental Python feedback release — 2026-10-16

Native AUTO/BAL and the saved bw10 startup gains remain available. Python AUTO/BAL
are experimental and use the current executor-v6-measuredrail firmware. No flash
is needed or was performed. This is a separate release from the preserved native
operator release.

Python AUTO completed a 25-second 250 Hz hardware run: capture at 3.172 seconds,
then continuous balance for the remaining 21.816 seconds, followed by counted
return home. Other trials exposed a host-cadence stop and an early right-switch
trip. Physical switch release and full two-switch homing subsequently succeeded:
619.2375 mm measured travel, home epoch 14, direct upright reference 330 retained.
Later trials exposed repeated host scheduling gaps and a brief capture loss. A matched native AUTO trial held 22.52 s after capture in 2.476 s. Repeatable Python AUTO commissioning remains incomplete. Python BAL is tested in
simulation/software; a standalone physical BAL test is pending.

From this directory, open the stopped console with:

```sh
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250
```

`python-auto 25` explicitly runs the Python controller; `auto 25` runs the
preserved native controller. A normal Python run stops; `rehome` is an explicit
separate command. Counted rehome is not proof of physical step tracking. The
console applies its saved working gain profile on startup; tests log actual
live parameters before motion.

Firmware source and the original firmware/vision fixtures needed by tests are
included for reproducibility. Their inclusion does not trigger any upload.
Historical archives are copied unchanged except the separately authorized SSH
username change in the tunnel helper. No vision service was redeployed.

See docs/python-control-20261016.md and the repository's
`evidence/python-control-id-20261016/` for run records and identification results.
This snapshot's release-manifest.json records every packaged file's SHA256.

An optional bounded observation-gap allowance is available only to explicit trusted runner callers; the console remains strict. The SDK also fixes STOP acknowledgement handling after an expired action, preserving the fault latch and requiring its own acknowledgement plus a disabled state. Neither change extends the firmware command lease.

Timing experiments exposed intermittent host command delays, including action-lease expiry. Temporary CPU separation helped but did not eliminate failures. A wire-equivalent standard-library CRC fast path reduces overhead; its final 20 s zero-command and 25 s AUTO checks passed. AUTO captured at 3.172 s, held 21.816 s, and returned home. One 8 ms gap stayed within the explicit experimental allowance. All camera CPU settings were restored. This is limited commissioning evidence, not a reliability certification. The user requested parking further timing investigation while system identification proceeds.

The new protocol checksum is checked against the original bitwise algorithm for every empty/one/two-byte input and seeded full-length inputs. An independently reviewed CLI regression was fixed so the new controller does not inherit legacy-only parameter constraints. See the final verification records in the evidence bundle for the complete suite outcome.
