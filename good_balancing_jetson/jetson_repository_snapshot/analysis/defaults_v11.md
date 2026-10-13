# v11 requested defaults

User requested vmax=0.8 m/s, amax_s=amax_b=16 m/s², jmax=70 m/s³.
For the 20T GT2 pulley: 1200 RPM, 24000 RPM/s, 105000 RPM/s².
Firmware, configuration JSON, current simulator defaults, and documentation agree.
The existing 7 µs pulse generator, 270 mm operating range, return-inside recovery,
manual limits, and stop/disable behavior remain as in v10.

Motion-governor tests and all 11 simulator test groups pass. ESP32 compilation
is checked before installation. This limit change does not establish reliable
physical swing-up or sustained balance. Source update only; not flashed by the assistant.
Historical v10 assessments and recorded-state results describe their original limits.
