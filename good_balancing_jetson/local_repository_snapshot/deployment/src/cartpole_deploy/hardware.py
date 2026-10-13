"""Synchronous commissioning client; imports and passive connections never arm."""
from __future__ import annotations

from collections import deque
import math
import secrets
import select
import socket
import threading
import time
from typing import Iterator

from .protocol import (DeviceError, FrameDecoder, ProtocolError, TransportError,
                       UINT32_MAX, encode_frame, parse_info, parse_state)
from .types import Observation


class HardwareRig:
    """Own one private D1 TCP connection, or an explicitly requested USB port.

    A request timeout is uncertain delivery, never a reason to repeat an action.
    Close disarms only sessions this instance explicitly attempted to arm. MCU
    leases, physical limits and faults remain authoritative at all times.
    """

    def __init__(self, host: str = '192.168.50.2', port: int = 9000,
                 timeout: float = 1.0, serial_port: str | None = None):
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be finite and positive')
        self.timeout = float(timeout)
        self._lock = threading.RLock()
        self._socket = None
        self._serial = None
        self._closed = False
        self._decoder = FrameDecoder()
        self._pending = deque()
        self._last_observation = None
        self._owns_arm = False
        self._session = 0
        self._previous_session = 0
        self._sequence = 0
        self._rail_half_m = .15
        self._stream_hz = 0
        try:
            if serial_port is None:
                self._socket = socket.create_connection((host, port), self.timeout)
                self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            else:
                # No pyserial dependency or device opening occurs on import.
                try:
                    import serial
                except ImportError as exc:
                    raise ImportError('USB transport requires optional pyserial') from exc
                self._serial = serial.Serial(serial_port, baudrate=115200,
                                             timeout=self.timeout, write_timeout=self.timeout)
            self._info = parse_info(self._request('info'))
            self._rail_half_m = self._info['rail_half_m']
        except (OSError, ProtocolError, DeviceError, TransportError):
            self._disconnect()
            raise

    def _disconnect(self) -> None:
        self._closed = True
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self._serial is not None:
            try:
                self._serial.close()
            except OSError:
                pass
            self._serial = None
        self._pending.clear()

    def _remaining(self, deadline: float) -> float:
        if self._closed:
            raise TransportError('transport is closed')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TransportError('response deadline expired; delivery may be uncertain')
        return remaining

    def _write(self, payload: str, deadline: float) -> None:
        remaining = self._remaining(deadline)
        data = encode_frame(payload)
        if self._socket is not None:
            self._socket.settimeout(remaining)
            self._socket.sendall(data)
        else:
            self._serial.write_timeout = remaining
            if self._serial.write(data) != len(data):
                raise TransportError('incomplete USB write; delivery may be uncertain')
        self._remaining(deadline)

    def _ingest(self, data: bytes) -> None:
        self._pending.extend(self._decoder.feed(data))
        if len(self._pending) > 64:
            raise ProtocolError('response queue overflow')

    def _read_bytes(self, deadline: float) -> None:
        remaining = self._remaining(deadline)
        if self._socket is not None:
            self._socket.settimeout(remaining)
            data = self._socket.recv(256)
        else:
            self._serial.timeout = remaining
            data = self._serial.read(max(1, min(256, self._serial.in_waiting)))
        if not data:
            raise TransportError('connection closed or timed out')
        self._ingest(data)
        self._remaining(deadline)

    def _remember_state(self, payload: str) -> Observation:
        observation = parse_state(payload)
        if self._last_observation is not None:
            delta = (observation.time_us - self._last_observation.time_us) & UINT32_MAX
            if delta >= 0x80000000:
                raise ProtocolError('MCU sample time moved backwards; reconnect after reset')
        self._last_observation = observation
        return observation

    def _drain(self, deadline: float) -> None:
        """Discard already queued stream state before requesting fresh telemetry."""
        drained_bytes = 0
        while True:
            self._remaining(deadline)
            while self._pending:
                payload = self._pending.popleft()
                if payload.startswith('D1 S '):
                    self._remember_state(payload)
                else:
                    raise ProtocolError('unexpected queued response')
            if self._socket is not None:
                ready = bool(select.select([self._socket], [], [], 0)[0])
            else:
                ready = self._serial.in_waiting > 0
            if not ready:
                return
            self._read_bytes(deadline)
            drained_bytes += 256
            if drained_bytes > 8192:
                raise ProtocolError('telemetry backlog exceeds fresh-request bound')

    def _receive(self, expected: str, deadline: float, accepted: int | None = None) -> str:
        while True:
            self._remaining(deadline)
            if not self._pending:
                self._read_bytes(deadline)
                continue
            payload = self._pending.popleft()
            if payload.startswith('D1 S '):
                self._remember_state(payload)
                if expected == 'state':
                    return payload
                continue
            fields = payload.split(' ')
            if len(fields) >= 3 and fields[:2] == ['D1', 'ERR'] and all(fields):
                raise DeviceError(fields[2], ' '.join(fields[3:]))
            if expected == 'info' and payload.startswith('D1 I '):
                return payload
            if expected not in ('info', 'state') and len(fields) >= 3 and fields[:3] == ['D1', 'OK', expected]:
                if len(fields) == 3:
                    return payload
                if (len(fields) == 4 and expected in ('arm', 'act') and accepted is not None
                        and fields[3].isascii() and fields[3].isdigit() and int(fields[3]) == accepted):
                    return payload
                raise ProtocolError('invalid acknowledgement argument')
            raise ProtocolError('unexpected response to ' + expected)

    def _request(self, command: str, deadline: float | None = None,
                 accepted: int | None = None) -> str:
        with self._lock:
            deadline = time.monotonic() + self.timeout if deadline is None else deadline
            try:
                self._drain(deadline)
                self._write('D1 ' + command, deadline)
                return self._receive(command.split()[0], deadline, accepted)
            except (OSError, TransportError) as exc:
                self._disconnect()
                if isinstance(exc, TransportError):
                    raise
                raise TransportError('transport failed; delivery may be uncertain') from exc
            except ProtocolError:
                self._disconnect()
                raise

    def capabilities(self) -> dict:
        return dict(self._info)

    def read(self) -> Observation:
        with self._lock:
            self._request('state')
            return self._last_observation

    def home(self, rail_half_m: float = .15) -> None:
        if (isinstance(rail_half_m, bool) or not math.isfinite(rail_half_m)
                or not .03 <= rail_half_m <= self._info['rail_half_m']):
            raise ValueError('manual home half-span must be 0.03..hardware maximum metres')
        with self._lock:
            self._request(f'home {rail_half_m:.9g}')
            self._rail_half_m = float(rail_half_m)

    def arm(self, session: int | None = None) -> None:
        with self._lock:
            if self._owns_arm:
                raise ValueError('this client already owns an armed session; stop first')
            if session is None:
                session = secrets.randbelow(UINT32_MAX) + 1
                while session == self._previous_session:
                    session = secrets.randbelow(UINT32_MAX) + 1
            if (isinstance(session, bool) or not isinstance(session, int)
                    or not 1 <= session <= UINT32_MAX or session == self._previous_session):
                raise ValueError('session must be a new nonzero uint32')
            state = self.read()
            if state.mode != 'DISARMED' or not state.homed or not state.encoder_valid:
                raise ValueError('arming requires disarmed, manually homed, valid encoder state')
            # An uncertain arm delivery still belongs to this client for cleanup.
            self._owns_arm = True
            self._session = self._previous_session = session
            self._sequence = 0
            try:
                self._request(f'arm {session}', time.monotonic() + min(self.timeout, .1), accepted=session)
            except DeviceError:
                self._owns_arm = False
                self._session = 0
                raise

    def command(self, kind: str, value: float, ttl_ms: int = 50) -> None:
        with self._lock:
            codes = {'acceleration': 'a', 'velocity': 'v', 'position': 'x'}
            if kind not in codes or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError('action must have a known kind and finite SI value')
            if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or not 10 <= ttl_ms <= 100:
                raise ValueError('ttl_ms must be an integer in 10..100')
            limits = {'acceleration': self._info['max_acceleration_m_s2'],
                      'velocity': self._info['max_velocity_m_s'],
                      'position': self._rail_half_m - .015}
            if abs(value) > limits[kind]:
                raise ValueError('action exceeds commissioning limits')
            if not self._owns_arm or not self._session:
                raise ValueError('explicit arm required before an action')
            if self._sequence == UINT32_MAX:
                raise ValueError('sequence exhausted; stop, home and arm a new session')
            # Include fresh sample acquisition and ACK in the action budget. This
            # is conservative; only the MCU can establish its actual sample age.
            deadline = time.monotonic() + min(self.timeout, ttl_ms / 1000)
            self._request('state', deadline)
            state = self._last_observation
            if (state.mode not in ('ARMED', 'RUNNING') or state.session != self._session
                    or not state.encoder_valid or not state.homed or not state.enabled):
                raise ValueError('fresh state no longer permits this armed action')
            self._sequence = max(self._sequence, state.sequence)
            if self._sequence == UINT32_MAX:
                raise ValueError('sequence exhausted; stop, home and arm a new session')
            self._sequence += 1  # Burn sequences even after uncertain/rejected delivery.
            self._request(f'act {self._session} {self._sequence} {state.time_us} '
                          f'{ttl_ms} {codes[kind]} {value:.9g}', deadline, self._sequence)

    def stop(self) -> None:
        with self._lock:
            self._request('stop')
            self._owns_arm = False
            self._session = 0

    def clear_fault(self) -> None:
        with self._lock:
            self._request('clear')
            self._owns_arm = False
            self._session = 0

    def set_stream_rate(self, hz: int) -> None:
        if (isinstance(hz, bool) or not isinstance(hz, int)
                or not 0 <= hz <= self._info['max_stream_hz']):
            raise ValueError('stream rate must be an integer in 0..hardware maximum Hz')
        with self._lock:
            self._request(f'stream {hz}')
            self._stream_hz = hz

    def iter_observations(self) -> Iterator[Observation]:
        """Yield received encoder/state samples; never send or renew actions."""
        if not self._stream_hz:
            raise ValueError('enable a stream rate before iterating observations')
        while not self._closed:
            with self._lock:
                try:
                    self._receive('state', time.monotonic() + self.timeout)
                except (OSError, TransportError) as exc:
                    self._disconnect()
                    raise TransportError('stream failed or timed out') from exc
                except ProtocolError:
                    self._disconnect()
                    raise
                observation = self._last_observation
            yield observation

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if self._owns_arm:
                    self._request('stop', time.monotonic() + min(self.timeout, .1))
            except (TransportError, ProtocolError, DeviceError):
                pass  # Disconnect and MCU expiry remain the final fallback.
            finally:
                self._owns_arm = False
                self._session = 0
                self._disconnect()

    def __enter__(self) -> HardwareRig:
        if self._closed:
            raise TransportError('transport is closed')
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
