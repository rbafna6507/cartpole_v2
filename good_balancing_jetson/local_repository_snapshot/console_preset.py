"""Restore a saved tuning preset while stopped; never restore pose or start motion."""
import hashlib
import json
import math
from pathlib import Path
import time

TUNABLES = frozenset('spin_trip_rad_s spin_resume_rad_s bal_pw leff pw pz pc1 pc2 '
                    'vmax_s vmax_b approach_v catch_v approach_angle catch_da vmax '
                    'amax_s amax_b amax_m jmax_m phase_soft jmax ke kpx kdx catch_a '
                    'catch_r giveup rail bw vman zvmax zamax ztravel'.split())
GAINS = frozenset('k1 k2 k3 k4 bal_k1 bal_k2 bal_k3 bal_k4'.split())


def load_preset(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('preset must use schema 1')
    if not isinstance(data.get('firmware'), str) or not data['firmware'].strip():
        raise ValueError('preset must identify the expected firmware')
    if not isinstance(data.get('settings'), dict) or not data['settings']:
        raise ValueError('preset settings must be a nonempty object')
    for field, allowed in (('settings', TUNABLES), ('computed_gains', GAINS)):
        values = data.get(field, {})
        if not isinstance(values, dict):
            raise ValueError(f'{field} must be an object')
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f'{key}: unsupported preset key; calibration and direct gains are not restored')
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{key}: expected a finite number')
    data['_source_path'] = str(path)
    data['_source_sha256'] = hashlib.sha256(raw).hexdigest()
    return data


def apply_startup_preset(link, preset, timeout=3.0):
    started = time.monotonic()
    connection = link._connected_at
    board_time = None

    def send(command):
        if not link.send(command):
            raise RuntimeError(f'preset command failed: {command}')

    def wait(predicate, description):
        nonlocal board_time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if link.rx_error or not link.alive or link._connected_at != connection:
                raise RuntimeError('connection changed during preset restoration; restart console')
            error = link.last_firmware_error
            if error and error[0] >= started:
                raise RuntimeError(f'firmware rejected preset: {error[1]}')
            with link.lock:
                if link.buf['t_ms']:
                    now = link.buf['t_ms'][-1]
                    if board_time is not None and now < board_time:
                        raise RuntimeError('board reset during preset restoration')
                    board_time = now
                if predicate():
                    return
            time.sleep(.01)
        raise RuntimeError(f'timed out waiting for {description}')

    def stopped():
        sent = time.monotonic()
        send('stop')
        wait(lambda: link.last_stop_ack_at is not None and link.last_stop_ack_at >= sent,
             'fresh STOP acknowledgment')
        sequence = link.encoder_sequence
        send('enc')
        wait(lambda: link.encoder_sequence > sequence and
             link.last_telemetry_at is not None and link.last_telemetry_at >= sent,
             'fresh stopped telemetry and driver state')
        with link.lock:
            encoder = dict(link.encoder_samples[-1])
            state = {k: v[-1] for k, v in link.buf.items() if v}
        if encoder['enabled'] != 0 or state.get('mode') != 0 or abs(state.get('v', math.inf)) > .0001:
            raise RuntimeError('preset requires IDLE, zero commanded velocity, and disabled drivers')
        return state, encoder

    def read_params(keys):
        sent = time.monotonic()
        send('params')
        # bal_k4 is the final line of the known v33 parameter response.
        required = set(keys) | {'encoder_upright_raw', 'bal_k4'}
        wait(lambda: all(link.parameter_seen_at.get(k, 0) >= sent for k in required) and
             link.firmware_seen_at >= sent, 'complete fresh parameter readback')
        if link.firmware_id != preset['firmware']:
            raise RuntimeError(f'firmware mismatch: expected {preset["firmware"]}, got {link.firmware_id}')
        with link.lock:
            return {k: v for k, v in link.params.items() if link.parameter_seen_at.get(k, 0) >= sent}

    try:
        send('rate 25')
        stopped()
        expected = {**preset['settings'], **preset.get('computed_gains', {})}
        before = read_params(expected)
        for key, value in preset['settings'].items():
            sent = time.monotonic()
            send(f'set {key} {value:.9g}')
            wait(lambda: link.parameter_seen_at.get(key, 0) >= sent, f'{key} acknowledgment')
            if not math.isclose(link.params[key], value, rel_tol=1e-6, abs_tol=5e-5):
                raise RuntimeError(f'{key} readback mismatch: wanted {value}, got {link.params[key]}')
        after = read_params(expected)
        for key, value in expected.items():
            if not math.isclose(after[key], value, rel_tol=1e-6, abs_tol=5e-5):
                raise RuntimeError(f'{key} readback mismatch: wanted {value}, got {after[key]}')
        if after['encoder_upright_raw'] != before['encoder_upright_raw']:
            raise RuntimeError('encoder reference changed during restoration')
        state, encoder = stopped()
        return {'preset_path': preset['_source_path'], 'preset_sha256': preset['_source_sha256'],
                'firmware': link.firmware_id, 'verified_at_unix_s': time.time(),
                'before': before, 'after': after, 'state': state, 'encoder': encoder,
                'restored_settings': dict(preset['settings']),
                'note': 'Parameters verified; no motion, home, or encoder-calibration command sent.'}
    except BaseException:
        link.send('stop')
        raise
