"""Native oracle of the archived Teensy sketch, compiled independently of Python.

Compilation is required and errors are fatal. Generated source and binaries live
in a temporary directory; no archive file is edited. This is controlTick fidelity,
not simulation of pulse interrupts, peripheral timing, or firmware scheduling.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'archive/good_balancing_jetson/teensy_firmware/teensy_swingup'
NATIVE = ROOT / 'tests/native'
PARAMETERS = frozenset('leff pw pz bal_pw pc1 pc2 vmax vmax_s vmax_b approach_v catch_v approach_angle catch_da amax_s amax_b jmax amax_m jmax_m ke kpx kdx phase_soft catch_a catch_r giveup spin_trip_rad_s spin_resume_rad_s rail bw vman'.split())
SUBSTITUTIONS = (
    ('native interrupt mask',
     '  uint32_t mask;asm volatile("mrs %0, primask" : "=r"(mask) :: "memory");return mask;',
     '  return 0;'),
    ('decoded angle input',
     '  return encoder_reference::angle_from_upright(enc_last_raw, ENC_INVERT != 0, enc_upright_raw);',
     '  return oracle_theta;'),
    ('calibrated cart position input',
     '    xc = (ax_pos[AX_CART] - home_steps) / CART_STEPS_PER_M;',
     '    xc = oracle_x;'),
    ('observe pre-governor demand',
     '      motion = cart_motion::advance(motion, xc, a, mode_speed, drive_amax,',
     '      oracle_demand = a;\n      motion = cart_motion::advance(motion, xc, a, mode_speed, drive_amax,'),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_source() -> tuple[str, dict]:
    source_path = ARCHIVE / 'teensy_swingup.ino'
    original = source_path.read_bytes()
    source = original.decode()
    substitutions = []
    for name, before, after in SUBSTITUTIONS:
        count = source.count(before)
        if count != 1:
            raise RuntimeError(f'oracle source substitution {name!r}: expected 1 exact match, found {count}')
        source = source.replace(before, after, 1)
        substitutions.append({'purpose': name, 'count': count, 'before': before, 'after': after})
    provenance = {
        'schema': 1,
        'oracle': 'whole archived .ino included in C++17 translation unit; original math and state-machine headers',
        'source': str(source_path.relative_to(ROOT)),
        'source_sha256': _sha(original),
        'generated_source_sha256': _sha(source.encode()),
        'substitutions': substitutions,
        'original_headers_sha256': {str(p.relative_to(ROOT)): _sha(p.read_bytes()) for p in sorted(ARCHIVE.glob('*.h'))},
        'python_support_sha256': _sha(Path(__file__).read_bytes()),
        'native_support_sha256': {str(p.relative_to(ROOT)): _sha(p.read_bytes()) for p in sorted(NATIVE.iterdir()) if p.is_file()},
        'compiler_flags': ['-std=c++17', '-O2', '-fno-fast-math'],
        'reset': 'fresh native controller state, wrapped decoded theta/estimate, zero command motion/recoveries/watch, IDLE, energy=-1, healthy encoder, ready timer; parameters persist',
        'tick': 'command handleLine with supplied health, optional host refresh, original encUpdate via Wire1 stub, original controlTick; fixed original DT=0.001; uint32 micros/millis derived from unwrapped supplied clock',
        'scope_exclusions': ['I2C electrical and bus timing', 'encoder count decoding/calibration', 'step pulse ISR and actual cart tracking', 'serviceControl scheduling and deadline faults', 'EEPROM persistence', 'Ethernet/USB transport', 'LCD rendering', 'Z-axis physical motion'],
    }
    return source, provenance


def _number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('oracle inputs must be finite real numbers')
    return format(value, '.17g')


class NativeOracle:
    """Persistent native process with reset, tunables, tick, and header probes."""
    _builds: dict[tuple[str, str], tuple[tempfile.TemporaryDirectory, Path, dict]] = {}

    def __init__(self, *, compiler: str | None = None):
        self.compiler = compiler or shutil.which('c++') or '/usr/bin/c++'
        self.process = None
        self._last_now = None
        self._first_tick = True
        self.provenance = None

    def __enter__(self):
        if self.process is not None:
            return self
        source, provenance = generate_source()
        build_hash = _sha(json.dumps(provenance, sort_keys=True).encode())
        key = (self.compiler, build_hash)
        if key not in self._builds:
            temp = tempfile.TemporaryDirectory(prefix='cartpole-native-oracle-')
            build = Path(temp.name)
            (build / 'firmware_native.ino').write_text(source)
            executable = build / 'oracle'
            command = [self.compiler, '-std=c++17', '-O2', '-fno-fast-math', '-I', str(NATIVE), '-I', str(build), '-I', str(ARCHIVE), str(NATIVE / 'harness.cpp'), '-o', str(executable)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired) as exc:
                temp.cleanup()
                raise RuntimeError(f'required native oracle compilation failed: {exc}') from exc
            if result.returncode:
                temp.cleanup()
                raise RuntimeError(f'required native oracle compilation failed:\n{result.stdout}{result.stderr}')
            version = subprocess.run([self.compiler, '--version'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
            provenance['compiler'] = version
            self._builds[key] = (temp, executable, provenance)
        _, executable, self.provenance = self._builds[key]
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self.reset()
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        if process.poll() is None:
            process.stdin.write('quit\n')
            process.stdin.flush()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    def _request(self, line):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('native oracle is not running')
        self.process.stdin.write(line + '\n')
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise RuntimeError(f'native oracle exited: {self.process.stderr.read()}')
        result = json.loads(response)
        if 'error' in result:
            raise ValueError(result['error'])
        return result

    @staticmethod
    def _clock(now_us):
        if isinstance(now_us, bool) or not isinstance(now_us, int) or not 0 <= now_us <= 2**64-1:
            raise ValueError('now_us must be a nonnegative uint64 integer')
        return now_us

    def reset(self, theta=0.0, now_us=0):
        theta_text = _number(theta)
        now_us = self._clock(now_us)
        result = self._request(f'reset {theta_text} {now_us}')
        self._last_now = now_us
        self._first_tick = True
        return result

    def set_parameters(self, mapping: Mapping):
        values = dict(mapping)
        if set(values) - PARAMETERS:
            raise ValueError(f'unknown swing-control parameters: {sorted(set(values) - PARAMETERS)}')
        encoded = [(name, _number(value)) for name, value in values.items()]
        for name, value in encoded:
            self._request(f'param {name} {value}')

    def tick(self, theta, x, *, now_us, encoder_ok=True, host_fresh=True, command=None, command_value=0.0):
        theta_text, x_text, value_text = _number(theta), _number(x), _number(command_value)
        now_us = self._clock(now_us)
        if now_us < self._last_now or (now_us == self._last_now and not self._first_tick):
            raise ValueError('tick timestamps must advance except the first tick at reset time')
        if not isinstance(encoder_ok, bool) or not isinstance(host_fresh, bool):
            raise ValueError('health flags must be bool')
        if command not in (None, 'auto', 'bal', 'manual', 'v', 'stop', 'ping'):
            raise ValueError('unsupported controller command')
        result = self._request(f'tick {theta_text} {x_text} {now_us} {int(encoder_ok)} {int(host_fresh)} {command or "-"} {value_text}')
        self._last_now = now_us
        self._first_tick = False
        return result

    def probe(self, name, *numeric_args):
        arity = {'gains': 0, 'estimate': 5, 'motion': 11, 'stopping': 4}
        if name not in arity or len(numeric_args) != arity[name]:
            raise ValueError('unsupported probe or wrong argument count')
        return self._request(' '.join([name] + [_number(v) for v in numeric_args]))
