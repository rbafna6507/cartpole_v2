"""Bounded data collection through the same hardware/simulation SDK methods."""
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
import time

from .config import RigConfig


def capture_run(rig, config: RigConfig, output, *, mode='noise', seconds=10.0,
                sample_hz=100, execute=False, center_confirmed=False, secured_z=False,
                cart_clamped=False, amplitude_m=.005, frequency_hz=.3,
                release_s=None, angle_deg=25.0):
    """Record a NEW run directory. Simulation advances explicitly; hardware uses wall time.

    Passive acquisition never arms/stops a pre-existing controller. Active capture
    requires exclusive disabled state and explicit commissioning acknowledgements.
    All exceptional exits preserve partial data and disarm owned motion.
    """
    if mode not in ('noise', 'decay', 'drive'):
        raise ValueError('mode must be noise, decay, or drive')
    if not math.isfinite(seconds) or not 0 < seconds <= 600:
        raise ValueError('duration must be 0..600 seconds')
    if isinstance(sample_hz, bool) or not isinstance(sample_hz, int) or not 20 <= sample_hz <= 500:
        raise ValueError('sample_hz must be an integer from 20 through 500')
    ratio = 1/(sample_hz*config.control_dt_s)
    if not math.isclose(ratio, round(ratio), abs_tol=1e-8):
        raise ValueError('sample interval must be an integer number of control ticks')
    simulated = callable(getattr(rig, 'advance', None))
    if mode == 'decay' and not (simulated or cart_clamped):
        raise ValueError('physically clamp cart and pass cart_clamped=True for passive decay')
    if mode == 'drive':
        if not simulated and not (execute and center_confirmed and secured_z):
            raise ValueError('hardware drive requires --execute --center-confirmed --secured-z')
        if not math.isfinite(amplitude_m) or not 0 < amplitude_m <= min(.02, config.rail_half_m-.025):
            raise ValueError('drive amplitude must be positive and <=20 mm, with rail clearance')
        if not math.isfinite(frequency_hz) or not 0 < frequency_hz <= 1:
            raise ValueError('drive frequency must be 0..1 Hz')
        if sample_hz < 50:
            raise ValueError('drive needs at least 50 Hz refreshing a 50 ms action lease')
    if not math.isfinite(angle_deg) or not 5 <= abs(angle_deg) <= 75:
        raise ValueError('decay release magnitude must be 5..75 degrees')
    if release_s is not None and (not math.isfinite(release_s) or not 0 <= release_s < seconds):
        raise ValueError('release time must be inside capture interval')
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {
        'schema_version': 1, 'backend': 'simulation' if simulated else 'hardware',
        'mode': mode, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'requested_duration_s': seconds, 'requested_sample_hz': sample_hz,
        'config': config.to_dict(), 'capabilities': rig.capabilities(),
        'cart_clamped_asserted': bool(cart_clamped or (simulated and mode != 'drive')),
        'release_s': 0.0 if simulated and mode == 'decay' else release_s,
        'requested_release_angle_deg': angle_deg if mode == 'decay' else None,
        'drive_amplitude_m': amplitude_m if mode == 'drive' else None,
        'drive_frequency_hz': frequency_hz if mode == 'drive' else None,
        'position_note': 'Hardware position is inferred from commanded step pulses. Add synchronized independent tracking to measure drive behavior.',
        'status': 'started', 'samples': 0, 'deadline_misses': 0,
        'error': None, 'stop_error': None}
    metadata_path = directory/'metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n')
    own_motion = False
    try:
        if simulated:
            rig.stop()
            rig.reset(theta_rad=math.pi+math.radians(angle_deg) if mode == 'decay' else math.pi)
            rig.set_cart_clamped(mode != 'drive')
        initial = rig.read()
        if initial.enabled or initial.mode not in ('DISARMED',):
            raise ValueError('capture requires a disabled, fault-free rig; no existing experiment was stopped')
        if not initial.encoder_valid:
            raise ValueError('encoder must be valid before capture')
        if mode == 'drive':
            rig.home(config.rail_half_m)
            own_motion = True  # even an uncertain arm delivery needs a stop attempt
            rig.arm()
        fields = list(initial.to_dict()) + ['device_elapsed_s', 'host_elapsed_s',
                                            'host_read_ms', 'requested_kind', 'requested_value']
        dt = 1/sample_hz
        sample_count = int(math.ceil(seconds*sample_hz))+1
        # Extra centered samples let the commanded profile settle before disabling.
        settling_samples = sample_hz if mode == 'drive' else 0
        host_start = time.monotonic()
        previous_us = None
        device_elapsed = 0.0
        with (directory/'samples.csv').open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for index in range(sample_count+settling_samples):
                elapsed = index*dt
                if index:
                    if simulated:
                        rig.advance(dt)
                    else:
                        remaining = host_start+elapsed-time.monotonic()
                        if remaining > 0:
                            time.sleep(remaining)
                        elif remaining < -dt:
                            metadata['deadline_misses'] += 1
                read_start = time.monotonic()
                observation = rig.read()
                read_ms = (time.monotonic()-read_start)*1000
                if previous_us is not None:
                    delta = (observation.time_us-previous_us) & 0xffffffff
                    if delta == 0 or delta >= 0x80000000:
                        raise ValueError('duplicate or backwards device timestamp; capture stopped')
                    device_elapsed += delta/1e6
                previous_us = observation.time_us
                target = 0.0
                if mode == 'drive' and elapsed < seconds:
                    # Windowed sine starts and ends with zero position and velocity.
                    target = amplitude_m*math.sin(2*math.pi*frequency_hz*elapsed)*math.sin(math.pi*elapsed/seconds)**2
                row = observation.to_dict()
                row.update(device_elapsed_s=device_elapsed, host_elapsed_s=time.monotonic()-host_start,
                           host_read_ms=read_ms, requested_kind='position' if mode == 'drive' else '',
                           requested_value=target if mode == 'drive' else '')
                writer.writerow(row)
                f.flush()
                metadata['samples'] += 1
                if observation.mode == 'FAULT' or not observation.encoder_valid:
                    raise RuntimeError(f'capture stopped: mode={observation.mode}, fault={observation.fault}, encoder_valid={observation.encoder_valid}')
                if mode == 'drive':
                    rig.command('position', target, ttl_ms=50)
            if mode == 'drive' and (abs(observation.v_m_s) > .005 or abs(observation.a_m_s2) > .1):
                raise RuntimeError('commanded motion did not settle before capture deadline; stopping')
        metadata['status'] = 'complete'
    except BaseException as exc:
        metadata['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        metadata['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        stop_failure = None
        if own_motion:
            try:
                rig.stop()
            except Exception as exc:
                stop_failure = exc
                metadata['stop_error'] = f'{type(exc).__name__}: {exc}'
                metadata['status'] = 'stop_unconfirmed'
        metadata['ended_utc'] = datetime.now(timezone.utc).isoformat()
        metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n')
        if stop_failure is not None and metadata['error'] is None:
            raise RuntimeError('capture ended but driver stop was not confirmed; inspect rig and metadata') from stop_failure
    return directory
