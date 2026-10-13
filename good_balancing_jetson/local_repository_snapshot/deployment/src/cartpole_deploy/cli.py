"""Local commissioning commands. Simulation is the default backend."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

from .config import RigConfig


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path)
    p.add_argument('--backend', choices=['sim', 'hardware'], default='sim')
    p.add_argument('--host', default='192.168.50.2')
    p.add_argument('--port', type=int, default=9000)
    p.add_argument('--serial-port')
    commands = p.add_subparsers(dest='task', required=True)
    commands.add_parser('info', help='read capabilities and state; never enable')
    s = commands.add_parser('stream', help='print read-only timestamped state as JSON lines')
    s.add_argument('--sensor', choices=['state', 'encoder', 'imu'], default='state')
    s.add_argument('--seconds', type=float, default=10)
    s.add_argument('--hz', type=int, default=50)
    v = commands.add_parser('view', help='open the MuJoCo viewer (simulation only)')
    v.add_argument('--angle-deg', type=float, default=25)
    c = commands.add_parser('capture', help='collect a new noise/decay/drive run')
    c.add_argument('mode', choices=['noise', 'decay', 'drive'])
    c.add_argument('--output', type=Path, required=True)
    c.add_argument('--seconds', type=float, default=10)
    c.add_argument('--hz', type=int, default=100)
    c.add_argument('--angle-deg', type=float, default=25)
    c.add_argument('--release-s', type=float)
    c.add_argument('--amplitude-mm', type=float, default=5)
    c.add_argument('--frequency-hz', type=float, default=.3)
    c.add_argument('--cart-clamped', action='store_true')
    c.add_argument('--execute', action='store_true')
    c.add_argument('--center-confirmed', action='store_true')
    c.add_argument('--secured-z', action='store_true')
    c.add_argument('--measured-half-span-m', type=float)
    for task in ['analyze', 'fit', 'validate']:
        a = commands.add_parser(task)
        a.add_argument('csv', type=Path)
        a.add_argument('--output', type=Path, required=True)
        if task != 'analyze':
            a.add_argument('--release-s', type=float, required=True)
            a.add_argument('--cart-clamped', action='store_true', required=True)
        if task == 'validate':
            a.add_argument('--fit', type=Path, required=True)
        if task == 'fit':
            a.add_argument('--export-config', type=Path)
    e = commands.add_parser('export', help='write a NEW rig config from fit and optional validation')
    e.add_argument('--fit', type=Path, required=True)
    e.add_argument('--validation', type=Path)
    e.add_argument('--output', type=Path, required=True)
    return p


def _write_new(path, obj):
    with Path(path).open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')


def main(argv=None):
    args = _parser().parse_args(argv)
    rig = None
    try:
        config = RigConfig.load(args.config) if args.config else RigConfig()
        if args.task in ('fit', 'validate', 'analyze', 'export'):
            from .identification import fit_decay, validate_decay, inspect_capture, export_fit
            if args.task == 'fit':
                result = fit_decay(args.csv, release_s=args.release_s, cart_clamped=args.cart_clamped)
                if args.export_config:
                    export_fit(config, result, args.export_config)
            elif args.task == 'validate':
                result = validate_decay(args.csv, json.loads(args.fit.read_text()),
                                        release_s=args.release_s, cart_clamped=args.cart_clamped)
            elif args.task == 'analyze':
                result = inspect_capture(args.csv)
            else:
                fit = json.loads(args.fit.read_text())
                validation = json.loads(args.validation.read_text()) if args.validation else None
                export_fit(config, fit, args.output, validation)
                print(args.output)
                return 0
            _write_new(args.output, result)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        if args.task == 'view' and args.backend != 'sim':
            raise ValueError('viewer is simulation only')
        if args.task == 'capture' and args.mode == 'drive' and args.backend == 'hardware':
            if not (args.execute and args.center_confirmed and args.secured_z and args.measured_half_span_m is not None):
                raise ValueError('hardware drive requires --execute --center-confirmed --secured-z --measured-half-span-m')
            from dataclasses import replace
            config = replace(config, rail_half_m=args.measured_half_span_m)
        if args.backend == 'sim':
            from .simulation import SimRig
            rig = SimRig(config)
        else:
            from .hardware import HardwareRig
            rig = HardwareRig(host=args.host, port=args.port, serial_port=args.serial_port)
        if args.task == 'info':
            print(json.dumps({'capabilities': rig.capabilities(), 'state': rig.read().to_dict()}, indent=2))
        elif args.task == 'stream':
            if args.sensor == 'imu':
                raise ValueError('IMU is not implemented on this rig; use encoder or state. No synthetic IMU is provided.')
            if not math.isfinite(args.seconds) or not 0 < args.seconds <= 600 or not 1 <= args.hz <= 500:
                raise ValueError('stream duration must be 0..600 s and rate 1..500 Hz')
            dt = 1/args.hz
            if args.backend == 'sim' and not math.isclose(dt/config.control_dt_s, round(dt/config.control_dt_s), abs_tol=1e-8):
                raise ValueError('simulation stream interval must be an integer number of control ticks')
            start = time.monotonic()
            for i in range(int(args.seconds*args.hz)):
                if i:
                    if args.backend == 'sim':
                        rig.advance(dt)
                    else:
                        time.sleep(max(0, start+i*dt-time.monotonic()))
                obs = rig.read()
                value = obs.to_dict()
                if args.sensor == 'encoder':
                    value = {k: value[k] for k in ('time_us', 'theta_rad', 'omega_rad_s', 'encoder_raw', 'flags')}
                print(json.dumps(value, allow_nan=False), flush=True)
        elif args.task == 'view':
            import mujoco.viewer
            rig.reset(theta_rad=math.pi+math.radians(args.angle_deg))
            rig.set_cart_clamped(True)
            with mujoco.viewer.launch_passive(rig.model, rig.data) as viewer:
                while viewer.is_running():
                    start = time.monotonic()
                    with viewer.lock():
                        rig.advance(config.policy_dt_s)
                    viewer.sync()
                    time.sleep(max(0, config.policy_dt_s-(time.monotonic()-start)))
        elif args.task == 'capture':
            from .recording import capture_run
            print('Preparing capture. For physical decay, note the actual hands-off time in the recorded trace for fitting.', file=sys.stderr)
            output = capture_run(rig, config, args.output, mode=args.mode, seconds=args.seconds,
                                 sample_hz=args.hz, execute=args.execute, center_confirmed=args.center_confirmed,
                                 secured_z=args.secured_z, cart_clamped=args.cart_clamped,
                                 amplitude_m=args.amplitude_mm/1000, frequency_hz=args.frequency_hz,
                                 angle_deg=args.angle_deg, release_s=args.release_s)
            print(output)
        return 0
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; owned motion receives a best-effort stop, firmware lease remains authoritative.', file=sys.stderr)
        return 130
    finally:
        if rig is not None:
            rig.close()


if __name__ == '__main__':
    raise SystemExit(main())
