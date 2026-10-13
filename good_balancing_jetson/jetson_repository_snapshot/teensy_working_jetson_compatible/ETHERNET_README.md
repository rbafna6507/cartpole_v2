# Teensy swing-up: native Ethernet update

This bundle is based on your attached v33 firmware. Copy the `teensy_swingup`
folder into your project, and place `cartpole.py` and `angle_plot.py` together
at the project root. Keep a backup of your current folder first.

## Changes

Defaults: `ke 4`, `kpx 40`, `kdx 2`, `pw 6`, `pz 0.85`, `pc1 -3`,
`pc2 -4`, `bw 30`, `jmax 150`.
The separate upright-only `bal_pw=8` stays unchanged. No control equations,
encoder conventions, rail limits, stepper wiring, or LCD code changed.
`firmware_changes.diff` records edits to existing firmware files; the two
new Ethernet headers supply the transport.

The Copperhill carrier's native Teensy 4.1 Ethernet connection uses QNEthernet;
there is no W5500/SPI chip-select configuration. CAN functionality is unchanged.
Ethernet is for commands/telemetry, not flashing.

## Build and flash over USB

Install the library once (Arduino IDE Library Manager also works):

```bash
arduino-cli lib update-index
arduino-cli lib install 'QNEthernet@0.37.0'
arduino-cli compile \
  --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std \
  --output-dir build_teensy teensy_swingup
```

Then use your existing `flash_teensy teensy_swingup`, or your working
`arduino-cli upload` command with the correct USB port. Flashing still uses USB.

## Network setup

Defaults in `teensy_swingup/ethernet_config.h`:

- Teensy: **192.168.50.2**, mask **255.255.255.0**, TCP **9000**.
- Directly connected Mac/Jetson Ethernet interface: **192.168.50.1**, same mask.
- No gateway/DNS is needed for this dedicated cable. Keep Wi-Fi for internet.

On macOS, choose the Ethernet adapter in System Settings → Network → Details →
TCP/IP, select manual IPv4, and enter the computer address and mask above.
On Jetson, configure the wired interface in Network settings with the same
manual address. Do not assign the computer the Teensy's .2 address.
If using an existing LAN instead, edit the firmware address/mask/gateway to
unused addresses on that LAN and recompile. The Teensy does not run Tailscale.
Use an isolated cable or trusted LAN; this raw TCP endpoint has no authentication.

## Connect

Run from the project directory containing both Python files:

```bash
uv run --with pyserial --with matplotlib cartpole.py --host 192.168.50.2
```

Optional alternate port: `--tcp-port 9000`. USB still works:

```bash
uv run --with pyserial --with matplotlib cartpole.py --port /dev/cu.usbmodemYOUR_PORT
```

The Python console keeps its existing heartbeat, CRC checks, startup STOP
acknowledgment, plotting and CSV logging. `angle_plot.py` is included to resolve
the earlier missing-module error. You can also use
`--port socket://192.168.50.2:9000`.

## Ownership and disconnect behavior

Only one TCP client is accepted, and only while drivers are disabled and encoder
calibration is inactive. Stop via USB before switching to Ethernet. Once TCP
owns control, USB commands are rejected except `stop` and `off`. Either command
stops motion and closes the TCP session, discarding its pending commands.
Close the Ethernet console before attempting USB control again; its reconnect
behavior can otherwise reclaim the connection while idle.

An observed link loss or closed TCP connection invokes the existing `eStop()`.
A silent host/network failure is covered by the original **1500 ms host-command
watchdog**. This timeout was deliberately not changed. No automatic motion
restart is added. The existing foreground deadline and ISR stall guards remain.

TX and RX application work use fixed buffers and bounded service sizes. Full
TX queues drop complete telemetry frames rather than wait for a slow reader.
USB TX backpressure cannot prevent TCP telemetry. TCP packet splitting is
handled by the newline parser; oversized commands are discarded through newline.
Network-stack work can still add latency; a successful compile is not proof of
hardware real-time timing. This transports the existing on-Teensy controller;
it does not introduce a camera/RL control protocol or offload the 1 kHz loop.

## First board check

1. Put the cart at physical center before reset, as the existing firmware requires.
2. With motor power off, connect over Ethernet and verify telemetry and parameters.
3. Send `stop`. Disconnect the Ethernet cable and reconnect; confirm the firmware
   stays stopped and the console requires valid telemetry/STOP acknowledgment.
4. With clearance and the existing manual controls, do a low-speed check. Confirm
   cable removal disables drivers and that no control-deadline faults appear.
5. Only then try your existing swing-up sequence. Timing under network traffic,
   actual cable-loss latency, and Copperhill hardware operation need board testing.

## Validation

Compiled successfully for Teensy 4.1, 600 MHz, o2std, Teensy core 1.62.0 and
QNEthernet 0.37.0. Original `controlLog` truncation warnings remain unchanged.
All existing non-controller headers are byte-identical. Controller-header edits
are defaults only; controlTick, eStop and serviceControl are byte-identical.

Host tests cover a real loopback TCP round trip and unchanged USB arguments.
Mock transport tests cover ownership rejection, one-command service, split and
oversized lines, TX backpressure/frame drops and link-loss stop/discard behavior.
Mocks do not validate the Ethernet stack or board timing.

```bash
uv run --with pyserial --with matplotlib python -m unittest discover -s tests
g++ -std=c++17 -Itests -Iteensy_swingup tests/test_transport.cpp -o /tmp/test_transport
/tmp/test_transport
```
