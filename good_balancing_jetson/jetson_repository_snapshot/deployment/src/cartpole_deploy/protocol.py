"""Strict ASCII integrity framing for the private, unauthenticated D1 link."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable

from .types import Observation

MAX_FRAME_BYTES = 256
UINT32_MAX = 0xFFFFFFFF


class ProtocolError(ValueError):
    """A response violated framing or the advertised D1 schema."""


class DeviceError(RuntimeError):
    """The MCU rejected a request; its error code is available as ``code``."""

    def __init__(self, code: str, detail: str = ''):
        self.code = code
        self.detail = detail
        super().__init__(code + (': ' + detail if detail else ''))


class TransportError(ConnectionError):
    """Delivery or response is uncertain. Requests must not be retried silently."""


def crc16(data: bytes) -> int:
    """CRC16/CCITT-FALSE (poly 0x1021, initial 0xffff)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def encode_frame(payload: str) -> bytes:
    try:
        data = payload.encode('ascii')
    except (AttributeError, UnicodeEncodeError) as exc:
        raise ProtocolError('payload must be ASCII text') from exc
    if not data or any(c < 32 or c > 126 or c in (42, 64) for c in data):
        raise ProtocolError('payload contains framing or control characters')
    frame = b'@' + data + f'*{crc16(data):04X}\n'.encode('ascii')
    if len(frame) > MAX_FRAME_BYTES:
        raise ProtocolError('frame exceeds 256 bytes')
    return frame


def decode_frame(frame: bytes) -> str:
    if len(frame) > MAX_FRAME_BYTES or not re.fullmatch(rb'@([^\r\n*@]+)\*([0-9A-F]{4})\n', frame):
        raise ProtocolError('malformed frame')
    data, checksum = frame[1:-1].rsplit(b'*', 1)
    if any(c < 32 or c > 126 for c in data):
        raise ProtocolError('non-ASCII or control character')
    if crc16(data) != int(checksum, 16):
        raise ProtocolError('CRC mismatch')
    return data.decode('ascii')


class FrameDecoder:
    """Incremental bounded parser; oversized lines discard through newline."""

    def __init__(self):
        self._buffer = bytearray()
        self._discard = False

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[str]:
        output = []
        oversize = False
        for byte in data:
            if self._discard:
                if byte == 10:
                    self._discard = False
                continue
            self._buffer.append(byte)
            if len(self._buffer) > MAX_FRAME_BYTES:
                self._buffer.clear()
                self._discard = byte != 10
                oversize = True
                continue
            if byte == 10:
                frame = bytes(self._buffer)
                self._buffer.clear()
                output.append(decode_frame(frame))
        if oversize:
            raise ProtocolError('frame exceeds 256 bytes')
        return output


def _uint(text: str, maximum: int = UINT32_MAX) -> int:
    if not re.fullmatch(r'[0-9]+', text):
        raise ProtocolError('expected unsigned integer')
    value = int(text)
    if value > maximum:
        raise ProtocolError('integer out of range')
    return value


def _finite(values: Iterable[str]) -> list[float]:
    try:
        numbers = [float(value) for value in values]
    except ValueError as exc:
        raise ProtocolError('invalid number') from exc
    if not all(math.isfinite(number) for number in numbers):
        raise ProtocolError('nonfinite number')
    return numbers


def parse_state(payload: str) -> Observation:
    fields = payload.split(' ')
    if len(fields) != 14 or fields[:2] != ['D1', 'S'] or any(not f for f in fields):
        raise ProtocolError('invalid state field count or version')
    if fields[3] not in ('DISARMED', 'ARMED', 'RUNNING', 'FAULT'):
        raise ProtocolError('unknown mode')
    theta, omega, x, v, a = _finite(fields[4:9])
    if not re.fullmatch(r'[A-Za-z0-9_-]+', fields[13]):
        raise ProtocolError('invalid fault token')
    return Observation(time_us=_uint(fields[2]), mode=fields[3], theta_rad=theta,
                       omega_rad_s=omega, x_m=x, v_m_s=v, a_m_s2=a,
                       encoder_raw=_uint(fields[9], 4095), flags=_uint(fields[10], 7),
                       sequence=_uint(fields[11]), session=_uint(fields[12]),
                       fault=fields[13], position_source='commanded_steps')


def parse_info(payload: str) -> dict:
    fields = payload.split(' ')
    if len(fields) != 12 or fields[:3] != ['D1', 'I', '1'] or fields[-1] != 'encoder':
        raise ProtocolError('unsupported info schema or sensor')
    control, stream, teeth = (_uint(f) for f in fields[3:6])
    steps, rail, velocity, acceleration, jerk = _finite(fields[6:11])
    if not (0 < control <= 1000 and 0 < stream <= 500 and teeth > 0 and steps > 0
            and 0 < rail <= .15 and 0 < velocity <= .25 and 0 < acceleration <= 2
            and 0 < jerk <= 20):
        raise ProtocolError('invalid or unsupported hardware limits')
    return {'protocol_version': 1, 'control_hz': control, 'max_stream_hz': stream,
            'pulley_teeth': teeth, 'steps_per_m': steps, 'rail_half_m': rail,
            'max_velocity_m_s': velocity, 'max_acceleration_m_s2': acceleration,
            'max_jerk_m_s3': jerk, 'encoder': True, 'imu': False, 'z_motion': False,
            'position_source': 'commanded_steps',
            'command_kinds': ('acceleration', 'velocity', 'position')}
