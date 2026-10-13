#!/usr/bin/env python3
"""Arm the ESP32, capture a free swing, save CSV/JSON, and create plots."""
import argparse, csv, json, math, sys, time
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Install dependencies: python3 -m pip install pyserial numpy matplotlib")

FIELDS = ["seq","t_us","dt_us","raw","ticks","theta","omega","agc","status","i2c_errors"]

def port_or_detect(requested):
    if requested: return requested
    hints = ("usbserial", "usbmodem", "wch", "cp210", "uart")
    for p in list_ports.comports():
        if any(h in (p.device + " " + (p.description or "")).lower() for h in hints): return p.device
    raise SystemExit("No serial board found; pass --port /dev/cu.usbserial-...")

def smooth(y, n):
    """Centered moving average with reflected edges (no zero-padding sag)."""
    n = max(3, min(int(n) | 1, len(y) - (1 - len(y) % 2)))
    if n < 3:
        return np.asarray(y, dtype=float).copy()
    pad = n // 2
    padded = np.pad(np.asarray(y, dtype=float), pad, mode="reflect")
    return np.convolve(padded, np.ones(n) / n, mode="valid")

def extrema(t, y, min_gap_s, smooth_samples):
    # Turning points from derivative sign changes, guarded against encoder noise.
    ys = smooth(y, smooth_samples)
    candidates = np.where(np.diff(np.sign(np.diff(ys))) != 0)[0] + 1
    keep = []
    for i in candidates:
        if i < 3 or i > len(y)-4: continue
        if not keep or t[i] - t[keep[-1]] >= min_gap_s:
            keep.append(i)
        elif abs(ys[i] - np.median(ys)) > abs(ys[keep[-1]] - np.median(ys)):
            keep[-1] = i
    return np.asarray(keep, dtype=int), ys

def analyze(rows, smooth_ms=35.0):
    t = np.array([r[1] for r in rows], float) * 1e-6
    t -= t[0]
    theta = np.unwrap(np.array([r[5] for r in rows], float))
    dt = np.diff(t)
    center = float(np.median(theta[max(0, len(theta)//2):]))
    y = theta - center
    sample_rate = 1 / np.median(dt)
    smooth_samples = max(5, round(sample_rate * smooth_ms / 1000))
    idx, ys = extrema(t, theta, 0.18, smooth_samples)
    # Reject tiny late extrema and alternate maxima/minima; same-sign peaks are one period apart.
    amp = np.abs(ys[idx] - center) if len(idx) else np.array([])
    floor = max(0.015, 0.04 * float(np.max(np.abs(y))))
    idx = idx[amp >= floor]
    # Differences between extrema two apart are complete periods. This works
    # for odd or even numbers of detected peaks (unlike pairing half-periods).
    periods = t[idx[2:]] - t[idx[:-2]] if len(idx) >= 3 else np.array([])
    T = float(np.median(periods)) if len(periods) else float("nan")
    freq = 1/T if T > 0 else float("nan")
    leff = 9.80665 * (T/(2*math.pi))**2 if T > 0 else float("nan")
    peak_amp = np.abs(ys[idx] - center)
    decrements = np.log(peak_amp[:-2] / peak_amp[2:]) if len(peak_amp) >= 3 else np.array([])
    decrements = decrements[np.isfinite(decrements) & (decrements > 0)]
    delta = float(np.median(decrements)) if len(decrements) else float("nan")
    zeta = delta / math.sqrt((2*math.pi)**2 + delta**2) if delta == delta else float("nan")
    q = 1/(2*zeta) if zeta > 0 else float("nan")
    decay_tau = T/delta if delta > 0 and T > 0 else float("nan")
    pos = peak_amp[(ys[idx]-center) > 0]; neg = peak_amp[(ys[idx]-center) < 0]
    asym = (float(np.median(pos))-float(np.median(neg))) / max(float(np.median(peak_amp)),1e-9) if len(pos) and len(neg) else float("nan")
    seq = np.array([r[0] for r in rows], int)
    agc = np.array([r[7] for r in rows if r[7] >= 0], float)
    metrics = {
      "samples": len(rows), "duration_s": float(t[-1]), "sample_rate_hz": float(sample_rate),
      "timing_jitter_us_rms": float(np.std(dt)*1e6), "dropped_sequence_samples": int(np.sum(np.maximum(0,np.diff(seq)-1))),
      "equilibrium_encoder_rad": center, "peak_angle_deg": float(np.degrees(np.max(np.abs(y)))),
      "period_s": T, "frequency_hz": freq, "effective_length_m_small_angle": leff,
      "log_decrement_per_cycle": delta, "damping_ratio": zeta, "quality_factor_Q": q,
      "amplitude_decay_time_constant_s": decay_tau, "positive_negative_amplitude_asymmetry": asym,
      "encoder_lsb_deg": 360/4096, "agc_median": float(np.median(agc)) if len(agc) else None,
      "agc_min": float(np.min(agc)) if len(agc) else None, "agc_max": float(np.max(agc)) if len(agc) else None,
      "i2c_errors": int(rows[-1][9]), "turning_points_used": int(len(idx)),
    }
    omega_smooth = smooth(np.gradient(ys, t), smooth_samples)
    return t, theta, ys, omega_smooth, idx, periods, metrics

def finite_json(v):
    if isinstance(v, float) and not math.isfinite(v): return None
    return v

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--out", default="pendulum_characterization")
    ap.add_argument("--timeout", type=float, default=65)
    ap.add_argument("--smooth-ms", type=float, default=35,
                    help="plot/peak smoothing window in ms (default: 35)")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ser = serial.Serial(port_or_detect(args.port), args.baud, timeout=.25)
    time.sleep(.4); ser.reset_input_buffer(); ser.write(b"ARM\n")
    print("Armed. Keep the cart fixed; pull the pendulum 10-20 degrees, then release it.")
    rows, begun, reason, deadline = [], False, "host_timeout", time.time()+args.timeout
    try:
      while time.time() < deadline:
        line = ser.readline().decode("utf-8", "replace").strip()
        if not line: continue
        if line.startswith("BEGIN"):
            begun=True; print("Motion detected; recording...")
        elif line.startswith("D ") and begun:
            p=line[2:].split(",")
            if len(p)==len(FIELDS): rows.append([float(x) for x in p])
        elif line.startswith("END"):
            reason=line; break
        elif line.startswith(("READY","ARMED","FIELDS","QUIET")): print(line)
    except KeyboardInterrupt:
      reason="host_stop"
    finally:
      try:
        if reason in ("host_stop", "host_timeout"):
          ser.write(b"STOP\n")
      finally:
        ser.close()
    if len(rows) < 100: raise SystemExit("Too little data captured. Re-run and give the pendulum a clean release.")
    csv_path=out/f"pendulum_{stamp}.csv"
    with csv_path.open("w",newline="") as f:
        w=csv.writer(f); w.writerow(FIELDS); w.writerows(rows)
    t,theta,ys,omega_smooth,idx,periods,m=analyze(rows, args.smooth_ms); m["stop_reason"]=reason
    json_path=out/f"pendulum_{stamp}_metrics.json"
    json_path.write_text(json.dumps({k:finite_json(v) for k,v in m.items()},indent=2)+"\n")
    try:
      import matplotlib.pyplot as plt
      fig,ax=plt.subplots(3,1,figsize=(11,9),sharex=True)
      ax[0].plot(t,np.degrees(theta),lw=.45,color="0.75",alpha=.55,label="raw encoder")
      ax[0].plot(t,np.degrees(ys),lw=1.8,color="tab:blue",label=f"smoothed ({args.smooth_ms:g} ms)")
      ax[0].plot(t[idx],np.degrees(ys[idx]),"o",ms=4,label="turning points"); ax[0].set_ylabel("angle (deg)"); ax[0].legend()
      omega=np.array([r[6] for r in rows]); ax[1].plot(t,omega,lw=.4,color="0.8",alpha=.45,label="firmware estimate")
      ax[1].plot(t,omega_smooth,lw=1.6,color="tab:orange",label="smoothed derivative")
      ax[1].set_ylabel("angular speed (rad/s)"); ax[1].legend()
      if len(idx): ax[2].plot(t[idx],np.degrees(np.abs(ys[idx]-m["equilibrium_encoder_rad"])),"o-")
      ax[2].set_ylabel("peak amplitude (deg)"); ax[2].set_xlabel("time (s)"); ax[2].set_yscale("log"); ax[2].grid(True,which="both",alpha=.3)
      fig.suptitle(f"Pendulum free decay: T={m['period_s']:.4g}s, Leff={m['effective_length_m_small_angle']:.4g}m, zeta={m['damping_ratio']:.3g}")
      fig.tight_layout(); plot_path=out/f"pendulum_{stamp}.png"; fig.savefig(plot_path,dpi=180); plt.close(fig)
    except ImportError: plot_path=None
    print("\nResults")
    for k,v in m.items(): print(f"  {k}: {v}")
    print(f"\nCSV: {csv_path}\nMetrics: {json_path}" + (f"\nPlot: {plot_path}" if plot_path else ""))

if __name__ == "__main__": main()
