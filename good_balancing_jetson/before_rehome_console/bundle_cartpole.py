#!/usr/bin/env python3
"""
cartpole.py -- host-side console for the ESP32 cart-pole.

    python3 cartpole.py

Then, at the >>> prompt:

    data       live dashboard of everything the board is streaming
    control    drive the cart by hand: A / D keys (W / S for the screws)
    auto       swing-up, then balance, with the dashboard up
    stop       emergency stop (also: spacebar or ESC while a window is open)

Everything streamed is logged to ./logs/ as CSV, always, without being asked.

Requires: pip install pyserial matplotlib
"""

import argparse
import binascii
import csv
import json
import math
import os
import select
import sys
import termios
import threading
import time
import tty
from collections import deque
from datetime import datetime
from angle_plot import angle_series

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial missing.  pip3 install pyserial")

# Telemetry field order must match emitTelemetry() in the firmware.
FIELDS = ["t_ms", "mode", "theta", "theta_dot", "x", "v",
          "accel", "energy", "z1", "z2", "agc", "loop_us"]
MODES = ["IDLE", "MANUAL", "SWINGUP", "BALANCE", "FAULT", "RAIL_BRAKE", "RAIL_RETURN", "SPIN_BRAKE", "SPIN_CENTER", "SPIN_WAIT", "BAL_BRAKE", "BAL_CENTER"]
WINDOW_S = 10.0          # seconds of history kept for the plots


# --------------------------------------------------------------------------
# serial link
# --------------------------------------------------------------------------
class Link:
    """Owns the port. A reader thread parses lines into ring buffers and a CSV."""

    def __init__(self, port=None, baud=115200, logdir="logs", reconnect=True, verbose=True, require_checksum=True):
        self.port_name = port or self.autodetect()
        if not self.port_name:
            sys.exit("No ESP32 found. Plug it in, or pass --port /dev/cu.xxx")
        self.baud = baud
        self.verbose = verbose
        self.require_checksum = require_checksum
        self.bad_frames = 0
        self.checked_frames = 0
        self._good_telemetry = 0
        self._connected_at = time.monotonic()
        self._awaiting_stop = True
        self._link_retry_at = 0.0
        self._bad_frame_notice_at = 0.0
        self.auto_reconnect = reconnect
        self._stop_event = threading.Event()
        self.recovering = False
        self.last_stop_ack_at = None
        self._rx_pending = b""
        self._heartbeat_at = 0.0
        self._stale_stop_sent = False
        self.telemetry_rate = 25
        self.encoder_samples = deque(maxlen=1000)
        self.encoder_sequence = 0
        self.ser = self._open_port()
        self.lock = threading.Lock()
        self._send_lock = threading.Lock()
        self.buf = {k: deque(maxlen=20000) for k in FIELDS}
        self.t0 = None
        self.params = {}
        self.mode = "?"
        self.rx_count = 0
        self.rx_rate = 0.0
        self.last_telemetry_at = None
        self.rx_error = None
        self.alive = True

        os.makedirs(logdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.logpath = os.path.join(logdir, f"run_{stamp}.csv")
        self._logfile = open(self.logpath, "w", newline="")
        self._csv = csv.writer(self._logfile)
        self._csv.writerow(FIELDS)
        self.eventpath = os.path.join(logdir, f"run_{stamp}_events.jsonl")
        self._eventfile = open(self.eventpath, "w", buffering=1)
        self._event_lock = threading.Lock()
        self._log_event("session", "x is inferred from pulses; v/accel are commands, not measured cart motion")

        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()
        time.sleep(0.3)

    def _log_event(self, direction, text):
        with self._event_lock:
            self._eventfile.write(json.dumps({"host_time_s": time.time(),
                                              "direction": direction, "text": text}) + "\n")

    @staticmethod
    def autodetect():
        hints = ("usbserial", "SLAB", "wchusbserial", "usbmodem", "UART")
        for p in list_ports.comports():
            if any(h.lower() in p.device.lower() or h.lower() in (p.description or "").lower()
                   for h in hints):
                return p.device
        return None

    def _open_port(self):
        if self.port_name.startswith("socket://"):
            return serial.serial_for_url(self.port_name, timeout=0.1, write_timeout=0.5)
        return serial.Serial(self.port_name, self.baud, timeout=0.1,
                             write_timeout=0.5, exclusive=True)

    def _motion_block_reason(self):
        if self.rx_error:
            return f"serial device unavailable: {self.rx_error}"
        if self._awaiting_stop:
            return "waiting for a valid STOP acknowledgment"
        if not self.telemetry_rate:
            return "telemetry disabled; use rate 25 before motion"
        if self.last_telemetry_at is None:
            return "waiting for valid telemetry; v15 uses 115200 baud and checksummed replies"
        age = time.monotonic()-self.last_telemetry_at
        if age > 1.0:
            return f"STALE TELEMETRY: last valid sample {age:.1f}s ago ({self.bad_frames} rejected frames)"
        if self._good_telemetry < 3 or self.recovering:
            return "waiting for three consecutive valid telemetry samples"
        return ""

    def telemetry_warning(self):
        return self._motion_block_reason()

    def link_status(self):
        reason = self._motion_block_reason()
        return (f"{self.port_name} at {self.baud} baud; {self.rx_rate:.1f} valid samples/s; "
                f"{self.checked_frames} checked frames, {self.bad_frames} rejected. "
                + (f"BLOCKED: {reason}" if reason else "READY for a new motion command."))

    def _bad_frame(self, reason, raw):
        self.bad_frames += 1
        self._good_telemetry = 0
        self._log_event("parse_error", f"{reason}: {raw[:240]!r}")
        now = time.monotonic()
        if self.verbose and now-self._bad_frame_notice_at > 5:
            print(f"\n  ! Damaged serial reply ignored ({self.bad_frames} rejected). Type link for status.", flush=True)
            self._bad_frame_notice_at = now

    def _maybe_reconnected(self):
        if self.recovering and not self._awaiting_stop and self._good_telemetry >= 3:
            self.recovering = False
            self._log_event("serial_ready", "STOP acknowledged and telemetry verified; no motion restarted")
            print("  USB reconnected; STOP and fresh telemetry verified. Check cart center before restarting.", flush=True)

    def _reader(self):
        try:
            while self.alive:
                try:
                    self._read_loop()
                    return
                except (serial.SerialException, OSError) as exc:
                    if not self.alive:
                        return
                    self.rx_error = f"{type(exc).__name__}: {exc}"
                    self.rx_rate = 0.0
                    self._log_event("reader_error", self.rx_error)
                    self._logfile.flush()
                    print(f"\n  ! USB serial connection lost: {self.rx_error}", flush=True)
                    if not self.auto_reconnect or not self._recover_serial():
                        return
        except Exception as exc:
            if self.alive:
                self.rx_error = f"{type(exc).__name__}: {exc}"
                self._log_event("reader_error", self.rx_error)
                print(f"\n  ! SERIAL READER STOPPED: {self.rx_error}", flush=True)
        finally:
            self._logfile.flush()

    def _recover_serial(self):
        self.recovering = True
        with self._send_lock:
            try:
                self.ser.close()
            except Exception:
                pass
        while self.alive and not self._stop_event.wait(1.0):
            try:
                with self._send_lock:
                    if not self.alive:return False
                    self.ser = self._open_port()
                    self._rx_pending = b""
                    self.params.clear()
                    self.last_telemetry_at = None
                    self.last_stop_ack_at = None
                    self._stale_stop_sent = False
                    self._connected_at = time.monotonic()
                    self._good_telemetry = 0
                    self._awaiting_stop = True
                    self._link_retry_at = self._connected_at
                    # Never replay auto, jog, or prior motion commands.
                    for command in ("stop", f"rate {self.telemetry_rate}", "params"):
                        self.ser.write((command+"\n").encode())
                        self._log_event("tx", command)
                self.rx_error = None
                self._log_event("serial_reconnected", self.port_name + "; awaiting STOP acknowledgment")
                return True
            except (serial.SerialException, OSError):
                try:
                    self.ser.close()
                except Exception:
                    pass
        return False

    def _service_link(self):
        now = time.monotonic()
        # Never depend on receiving a parameter line to keep the host watchdog alive.
        if now-self._heartbeat_at >= 0.25:
            self.send("ping")
            self._heartbeat_at = now
        age = now-(self.last_telemetry_at if self.last_telemetry_at is not None else self._connected_at)
        stale = self.telemetry_rate and age > 1.0
        if stale and not self._stale_stop_sent:
            self._stale_stop_sent = True
            self.rx_rate = 0.0
            self._good_telemetry = 0
            self._log_event("telemetry_timeout", "No valid sample for 1s; STOP/recovery requested; no automatic motion restart")
        if (stale or self._awaiting_stop) and now-self._link_retry_at >= 1.0:
            self._awaiting_stop = True
            self._link_retry_at = now
            self.send("stop")
            self.send(f"rate {self.telemetry_rate}")

    def _read_loop(self):
        t_last, n_last = time.monotonic(), self.rx_count
        while self.alive:
            self._service_link()
            # Drain available bytes in chunks instead of readline's byte-by-byte reads.
            raw = self.ser.read(max(1, min(self.ser.in_waiting, 1024)))
            self._rx_pending += raw
            while b"\n" in self._rx_pending:
                line, self._rx_pending = self._rx_pending.split(b"\n", 1)
                if len(line) > 4096:
                    self._bad_frame("oversize frame", line)
                else:
                    self._consume_line(line)
            if len(self._rx_pending) > 4096:
                self._bad_frame("oversize/incomplete frame", self._rx_pending)
                self._rx_pending = b""
            now = time.monotonic()
            if now-t_last > 1.0:
                self.rx_rate = (self.rx_count-n_last)/(now-t_last)
                n_last, t_last = self.rx_count, now
                self._logfile.flush()

    def _consume_line(self, raw):
        raw = raw.rstrip(b"\r\n")
        if not raw:
            return
        if raw.startswith(b"@"):
            payload, separator, checksum = raw[1:].rpartition(b"*")
            try:
                if not separator or len(checksum) != 4 or any(c not in b"0123456789ABCDEFabcdef" for c in checksum):
                    raise ValueError("missing/invalid checksum")
                if binascii.crc_hqx(payload, 0xffff) != int(checksum, 16):
                    raise ValueError("checksum mismatch")
                line = payload.decode("ascii").strip()
            except (ValueError, UnicodeDecodeError) as exc:
                self._bad_frame(str(exc), raw)
                return
            self.checked_frames += 1
        elif self.require_checksum:
            self._bad_frame("unframed reply (flash v15; use 115200 baud)", raw)
            return
        else:
            line = raw.decode("utf-8", "replace").strip()
        if not line:
            return
        if line[0] != "T":
            self._log_event("rx", line)
        if line[0] == "T":
            parts = line.split()
            if len(parts) != len(FIELDS) + 1:
                self._bad_frame("telemetry field count", raw)
                return
            try:
                vals = [float(p) for p in parts[1:]]
                if not all(math.isfinite(v) for v in vals) or not vals[1].is_integer():
                    raise ValueError("non-finite telemetry or invalid mode")
            except ValueError:
                self._bad_frame("invalid telemetry number", raw)
                return
            with self.lock:
                if self.t0 is None:
                    self.t0 = vals[0]
                for k, val in zip(FIELDS, vals):
                    self.buf[k].append(val)
                m = int(vals[1])
                self.mode = MODES[m] if 0 <= m < len(MODES) else "?"
                self.rx_count += 1
                self.last_telemetry_at = time.monotonic()
                self._good_telemetry += 1
                if self._good_telemetry >= 3:
                    self._stale_stop_sent = False
            self._maybe_reconnected()
            self._csv.writerow(vals)
        elif line[0] == "E":
            parts = line.split()
            try:
                if len(parts)!=9:raise ValueError("encoder frame length")
                values=list(map(int,parts[1:]))
                if not 0<=values[1]<4096:raise ValueError("raw angle range")
            except ValueError:
                self._log_event("parse_error",line);return
            with self.lock:
                self.encoder_sequence+=1
                self.encoder_samples.append(dict(zip(
                    ["board_ms","raw","zero_raw","agc","status","i2c_errors","valid","enabled"],values),
                    sequence=self.encoder_sequence,host_time_s=time.time()))
        elif line[0] == "=":
            parts = line.split()
            if len(parts) == 3:
                try:
                    value = float(parts[2])
                    if not math.isfinite(value):
                        raise ValueError("non-finite parameter")
                except ValueError:
                    self._log_event("parse_error", line)
                    return
                with self.lock:
                    self.params[parts[1]] = value
                if self.verbose:
                    print(f"  {parts[1]} = {parts[2]}")
        elif line[0] in "#!":
            if line.startswith("# STOP") or line.startswith("# de-energized"):
                self.last_stop_ack_at = time.monotonic()
                self._awaiting_stop = False
                self._maybe_reconnected()
            if self.verbose:
                print(f"  {line}")


    def send(self, cmd):
        command = cmd.split()[0] if cmd.split() else ""
        if command in ("auto", "bal", "manual", "v", "zv", "on"):
            reason = self._motion_block_reason()
            if reason:
                self._log_event("motion_blocked", f"{cmd}: {reason}")
                print(f"  ! Motion blocked: {reason}. Type link for details.", flush=True)
                return False
        if command == "bal":
            if self.params.get("bal_fall_deg") != 50 or self.params.get("bal_start_deg") != 10:
                reason = "upright-only firmware not confirmed; upload v17 and refresh params before bal"
                self._log_event("motion_blocked", f"{cmd}: {reason}")
                print(f"  ! {reason}", flush=True)
                return False
            # Snapshot settings before the firmware's BALANCE acknowledgment.
            if not self.send("params"):
                return False
        if command == "rate":
            try:self.telemetry_rate=max(0,min(100,int(cmd.split()[1])))
            except (ValueError,IndexError):pass
        try:
            with self._send_lock:
                self._log_event("tx", cmd)
                self.ser.write((cmd + "\n").encode())
            return True
        except Exception as e:
            self._log_event("write_error", f"{cmd}: {e}")
            print(f"  ! write failed: {e}")
            return False

    def recent(self, seconds=WINDOW_S):
        """Return (t_rel, {field: list}) for the last `seconds` of samples."""
        with self.lock:
            if not self.buf["t_ms"]:
                return [], {}
            t = list(self.buf["t_ms"])
            cut = t[-1] - seconds * 1000.0
            i = 0
            for i in range(len(t) - 1, -1, -1):
                if t[i] < cut:
                    i += 1
                    break
            out = {k: list(self.buf[k])[i:] for k in FIELDS}
        tt = [(v - out["t_ms"][-1]) / 1000.0 for v in out["t_ms"]]
        return tt, out

    def close(self):
        try:
            self.send("stop")
            time.sleep(0.1)
        finally:
            self.alive = False
            self._stop_event.set()
            try:self.ser.close()
            except Exception:pass
            self.thread.join()
            self._logfile.close()
            self._eventfile.close()


# --------------------------------------------------------------------------
# keyboard: raw terminal reader, used alongside the plot window
# --------------------------------------------------------------------------
class RawKeys:
    """Non-blocking single-char reads from the terminal, restored on exit."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.saved = None
        self.eof = False

    def __enter__(self):
        if os.isatty(self.fd):
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, *a):
        if self.saved:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def poll(self):
        keys = []
        while not self.eof and select.select([self.fd], [], [], 0)[0]:
            chunk = os.read(self.fd, 4096)
            if not chunk:
                self.eof = True
                break
            keys.extend(chunk.decode("utf-8", "replace"))
        return keys


class PlotCommandInput:
    """Line commands while plotting; letters never become terminal jog keys."""
    def __init__(self, link, stop, quit_plot, echo=None):
        self.link, self.stop, self.quit_plot = link, stop, quit_plot
        self.buffer = ""
        self.echo = echo or (lambda text: print(text, end="", flush=True))

    def feed(self, key):
        if key in ("\x1b", "\x03") or (key == " " and not self.buffer):
            self.buffer = ""
            self.stop()
            self.echo("\r\nSTOP requested — check acknowledgment\nplot> ")
        elif key in ("\r", "\n"):
            command = self.buffer.strip()
            self.buffer = ""
            self.echo("\r\n")
            if command.lower() == "stop":
                self.stop()
            elif command.lower() in ("q", "quit", "exit"):
                self.quit_plot()
            elif command.lower() == "link":
                self.echo(self.link.link_status()+"\n")
            elif command:
                self.link.send(command)
            self.echo("plot> ")
        elif key in ("\x7f", "\b"):
            if self.buffer:
                self.buffer = self.buffer[:-1]
                self.echo("\b \b")
        elif key.isprintable() and len(self.buffer) < 95:
            self.buffer += key
            self.echo(key)


# --------------------------------------------------------------------------
# live dashboard
# --------------------------------------------------------------------------
def dashboard(link, interactive=False, title=""):
    """
    Blocking live plot. `interactive` enables A/D cart driving and W/S screws.

    Hold-to-move works through the firmware's 250 ms watchdog: plot key
    repeat keeps resending `v`, and the instant the
    repeat stops the board coasts to zero on its own. That means a crashed or
    disconnected host cannot leave the cart driving into the end of the rail.
    """
    if getattr(link, "text_mode", False) or (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")
    ):
        return text_dashboard(link, interactive)
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
        from matplotlib.widgets import Button
    except ImportError:
        return text_dashboard(link, interactive)

    jog_v = link.params.get("vman", 0.02)
    jog_z = link.params.get("zvmax", 2.0)
    held = {"key": None, "t": 0.0}
    quit_flag = {"q": False}
    jog_lock = threading.Lock()

    def stop_motion():
        with jog_lock:
            held["key"] = None
            link.send("stop")

    def quit_plot():
        stop_motion()
        quit_flag["q"] = True

    def press(k):
        if k in (" ", "escape", "\x1b"):
            stop_motion()
            print("\r  STOP requested — check acknowledgment")
        elif k == "q":
            quit_plot()
        elif interactive and k in ("a", "d", "w", "s"):
            held["key"], held["t"] = k, time.time()

    def release(k):
        if k == held["key"]:
            held["key"] = None

    try:
        fig, ax = plt.subplots(5, 1, figsize=(10, 9), sharex=True)
    except (ImportError, RuntimeError) as exc:
        print(f"  Graphical dashboard unavailable ({exc}); using text dashboard.")
        return text_dashboard(link, interactive)
    # Agg/PDF/SVG/inline canvases cannot run a desktop GUI event loop.
    # Detect before registering close handlers; closing this unused figure must
    # not send STOP. Real GUI close/EOF and watchdog stops remain in force.
    if not getattr(fig.canvas, "required_interactive_framework", None):
        plt.close(fig)
        print("  Non-interactive plotting backend; using text dashboard.")
        return text_dashboard(link, interactive)
    fig.canvas.manager.set_window_title("cart-pole" + (f" -- {title}" if title else ""))

    # Stop keys work in every plot, including read-only/automatic dashboards.
    fig.canvas.mpl_connect("key_press_event", lambda e: press(e.key))
    fig.canvas.mpl_connect("key_release_event", lambda e: release(e.key))
    fig.canvas.mpl_connect("close_event", lambda _: quit_plot())
    fig.subplots_adjust(bottom=0.12, top=0.94)
    stop_button = Button(fig.add_axes([0.76, 0.02, 0.21, 0.045]), "STOP / disable",
                         color="#ffb4a8", hovercolor="#ff7866")
    stop_button.on_clicked(lambda _: stop_motion())
    balance_button = Button(fig.add_axes([0.53, 0.02, 0.21, 0.045]), "START upright")
    balance_button.on_clicked(lambda _: link.send("bal"))
    fig.text(0.02, 0.035, "Terminal: bal / stop + Enter | Space / Esc: stop", fontsize=9)

    lines = {}
    lines["theta"], = ax[0].plot([], [], lw=1.4)
    ax[0].set_ylabel("theta (rad)\n0 = upright")
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].axhspan(-math.radians(10), math.radians(10), color="tab:green", alpha=0.10)
    for limit in (-math.radians(50), math.radians(50)):
        ax[0].axhline(limit, color="tab:red", ls="--", lw=0.8)
    ax[0].set_ylim(-3.3, 3.3)

    lines["theta_dot"], = ax[1].plot([], [], lw=1.2, color="tab:orange")
    ax[1].set_ylabel("theta_dot\n(rad/s)")
    ax[1].axhline(0, color="k", lw=0.6)

    lines["x"], = ax[2].plot([], [], lw=1.4, color="tab:blue", label="x (m)")
    lines["v"], = ax[2].plot([], [], lw=1.0, color="tab:cyan", alpha=0.8, label="v (m/s)")
    ax[2].set_ylabel("cart")
    ax[2].legend(loc="upper left", fontsize=8)
    rail = link.params.get("rail", 0.22)
    ax[2].axhline(rail, color="r", lw=0.8, ls="--")
    ax[2].axhline(-rail, color="r", lw=0.8, ls="--")

    lines["accel"], = ax[3].plot([], [], lw=1.0, color="tab:red")
    ax[3].set_ylabel("accel cmd\n(m/s^2)")
    ax[3].axhline(0, color="k", lw=0.6)

    lines["energy"], = ax[4].plot([], [], lw=1.4, color="tab:purple")
    ax[4].set_ylabel("energy / E_up")
    ax[4].axhline(1.0, color="g", lw=0.8, ls="--")
    ax[4].axhline(-1.0, color="k", lw=0.6)
    ax[4].set_ylim(-1.6, 2.2)
    ax[4].set_xlabel("seconds before now")

    status = fig.text(0.01, 0.985, "", fontsize=9, va="top", family="monospace")

    def update(_):
        if quit_flag["q"]:
            plt.close(fig)
            return list(lines.values()) + [status]
        with jog_lock:
            # keep the jog alive while a key is held down
            if interactive and held["key"]:
                if time.time() - held["t"] > 0.6:
                    held["key"] = None
                else:
                    k = held["key"]
                    if k == "a":
                        link.send(f"v {-jog_v:.3f}")
                    elif k == "d":
                        link.send(f"v {jog_v:.3f}")
                    elif k == "w":
                        link.send(f"zv {jog_z:.1f}")
                    elif k == "s":
                        link.send(f"zv {-jog_z:.1f}")

        warning = link.telemetry_warning()
        status.set_color("red" if warning else "black")
        t, d = link.recent()
        if not t:
            status.set_text(warning)
            return list(lines.values()) + [status]
        for key, ln in lines.items():
            if key == "theta":
                ln.set_data(*angle_series(t, d[key]))
            else:
                ln.set_data(t, d[key])
        for a in ax:
            a.set_xlim(-WINDOW_S, 0.4)
        for a, keys in ((ax[1], ["theta_dot"]), (ax[2], ["x", "v"]), (ax[3], ["accel"])):
            vals = [y for k in keys for y in d[k]] or [0, 1]
            lo, hi = min(vals), max(vals)
            pad = max(0.1, (hi - lo) * 0.15)
            a.set_ylim(lo - pad, hi + pad)

        status.set_text(warning or (
            f"mode {link.mode:<8} theta {d['theta'][-1]:+.3f}  x {d['x'][-1]:+.4f}m  "
            f"v {d['v'][-1]:+.3f}m/s  z {d['z1'][-1]:.1f}mm  "
            f"agc {int(d['agc'][-1])}  loop {int(d['loop_us'][-1])}us  "
            f"rx {link.rx_rate:.0f}Hz"
            + ("   [A/D cart  W/S screws  SPACE stop  Q quit]" if interactive else "   [SPACE / ESC stop  Q quit]")
        ))
        return list(lines.values()) + [status]

    anim = FuncAnimation(fig, update, interval=40, blit=False, cache_frame_data=False)

    print("\nPlot running. Type stop + Enter in this terminal, or click STOP in the plot.")
    commands = PlotCommandInput(link, stop_motion, quit_plot)
    finished = threading.Event()
    with RawKeys() as kb:
        commands.echo("plot> ")
        def pump():
            while not finished.is_set():
                for key in kb.poll():
                    commands.feed(key)
                if kb.eof:
                    quit_plot()
                    return
                finished.wait(0.02)
        worker = threading.Thread(target=pump, daemon=True)
        worker.start()
        try:
            plt.show(block=True)
        except KeyboardInterrupt:
            stop_motion()
        finally:
            finished.set()
            worker.join()
            quit_plot()
    del anim, stop_button


def text_dashboard(link, interactive=False):
    """Command-capable fallback when matplotlib is unavailable."""
    print("  Text dashboard: stop + Enter; Space/Esc stop; q + Enter exits.")
    done = threading.Event()
    def stop_motion():
        link.send("stop")
    def quit_plot():
        stop_motion()
        done.set()
    commands = PlotCommandInput(link, stop_motion, quit_plot)
    last_status = 0.0
    with RawKeys() as kb:
        commands.echo("plot> ")
        try:
            while not done.is_set():
                for key in kb.poll():
                    commands.feed(key)
                if kb.eof:
                    break
                if not commands.buffer and time.monotonic() - last_status > 1:
                    _, data = link.recent()
                    warning = link.telemetry_warning()
                    if warning:
                        print(f"\r{warning}\nplot> ", end="", flush=True)
                    elif data.get("theta"):
                        print(f"\rmode {link.mode}: theta {data['theta'][-1]:+.3f} rad, "
                              f"x {data['x'][-1]:+.4f} m, v {data['v'][-1]:+.3f} m/s\nplot> ",
                              end="", flush=True)
                    last_status = time.monotonic()
                time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            stop_motion()


# --------------------------------------------------------------------------
# REPL
# --------------------------------------------------------------------------
HELP = """
  data        live dashboard (read-only)
  control     drive the cart:  A / D  cart left-right,  W / S  screws up-down
              In plot: SPACE/Esc/STOP button stop, Q exits.
              In terminal while plotting: commands + Enter (including stop).
  auto        swing-up then balance, dashboard opens
  bal         upright trial -- start within 10deg; fall >50deg returns to center and stops
  stop        stop motion and disable all drivers (swing-up firmware)

  Swing-up firmware uses one set of defaults; use set to change limits.

  off / on    de-energize / energize all three drivers.
              WARNING: the SFU1605 screws back-drive. 'off' with the rail
              raised will let it sink. Support it first.

  home        call the cart's current position x = 0
  zhome       call the current rail height z = 0
  zero        hanging still: save down and update upright half a turn away
  upright     held straight up: save current encoder count as upright
  upright N   save explicit upright count N (0..4095); survives reset
  mag         AS5600 magnet health (status + AGC)
  stat        one-shot state dump
  params      list every live-tunable parameter
  set k v     stopped tuning: set bal_pw 7 (baseline) / set bal_pw 8 (candidate)
  get k       read one back
  rate hz     telemetry rate (default 25, maximum 100)
  link        serial health and exact motion-block reason
  log         path of the CSV being written right now
  q / quit    exit
"""


def repl(link):
    print(f"  connected: {link.port_name}")
    print(f"  logging:   {link.logpath}")
    print(f"  events:    {link.eventpath}")
    link.send("params")
    time.sleep(0.4)
    print("  'help' for commands.\n")

    while True:
        try:
            raw = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        word = raw.split()[0]

        if word in ("q", "quit", "exit"):
            break
        elif word == "help":
            print(HELP)
        elif word == "link":
            print("  " + link.link_status())
        elif word == "log":
            print(f"  {link.logpath}")
        elif word == "data":
            dashboard(link, interactive=False, title="data")
        elif word == "control":
            if not link.send("manual"):
                continue
            time.sleep(0.1)
            dashboard(link, interactive=True, title="manual control")
        elif word == "auto":
            if not link.send("auto"):
                continue
            time.sleep(0.1)
            dashboard(link, interactive=False, title="swing-up + balance")
        elif word == "bal":
            if not link.send("bal"):
                continue
            time.sleep(0.1)
            dashboard(link, interactive=False, title="balance")
        else:
            link.send(raw)          # everything else goes straight to the board
            time.sleep(0.15)


def main():
    ap = argparse.ArgumentParser(description="ESP32 cart-pole console")
    ap.add_argument("--port", help="serial device, e.g. /dev/cu.usbserial-0001")
    ap.add_argument("--text", action="store_true", help="terminal dashboard; use on Jetson/SSH without a GUI")
    ap.add_argument("--host", help="Teensy Ethernet IP; mutually exclusive with --port")
    ap.add_argument("--tcp-port", type=int, default=9000)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--rate", type=int, default=25, help="telemetry Hz (0–100)")
    ap.add_argument("--logdir", default="logs")
    ap.add_argument("--legacy-serial", action="store_true", help="allow unchecked replies from v14 or older (also specify its --baud)")
    args = ap.parse_args()
    if args.host and args.port:
        ap.error("use either --host or --port")
    if not 1 <= args.tcp_port <= 65535:
        ap.error("--tcp-port must be 1..65535")
    if args.host:
        args.port = f"socket://{args.host}:{args.tcp_port}"

    if not args.port:
        found = [p.device for p in list_ports.comports()]
        if found:
            print("  ports seen: " + ", ".join(found))

    if not 0 <= args.rate <= 100:
        ap.error("--rate must be 0–100")
    if args.legacy_serial:
        print("Legacy serial: damaged numeric replies cannot be reliably detected.")
    link = Link(args.port, args.baud, args.logdir, require_checksum=not args.legacy_serial)
    link.text_mode = args.text
    link.send(f"rate {args.rate}")
    try:
        repl(link)
    finally:
        print("  stopping.")
        link.close()


if __name__ == "__main__":
    main()
