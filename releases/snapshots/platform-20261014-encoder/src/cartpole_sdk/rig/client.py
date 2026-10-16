"""Exclusive stopped-on-connect live executor client with bounded board leases.

Only trusted operator code owns Rig. Policies receive observations and submit
ActionRequest objects through a broker, never this serial transport.
"""
from collections import deque, OrderedDict
from dataclasses import asdict, replace
import math
from pathlib import Path
import queue
import re
import secrets
import threading
import time

from cartpole_sdk.contracts import (ActionLimits, ActionRequest, Observation, Sample,
                                    Session, ValidationError, validate_action)
from cartpole_sdk.recording import canonical_json
from .protocol import (LineBuffer, ProtocolError, State, UINT32, decode, encode,
                       parse_state, parse_info, uint32, unwrap32)
from .transport import SerialTransport

class RigError(RuntimeError):
    """Stopped or latched live rig failure; recovery is always explicit."""

_OWNERS = set()
_OWNERS_LOCK = threading.Lock()
_RATE = (0, 100, 250, 500, 1000)
_NS_TICK = 1_000_000

class Rig:
    """Context management connects stopped and stops in finally.

    ``transport_factory`` is a trusted adapter injection point for PTY/TCP tests.
    A transport must have bounded reads and writes; default serial timeouts are
    5ms/50ms. Constructor and imports have no serial side effects.
    """
    def __init__(self, port='/dev/serial/by-id/cartpole', rate_hz=100, log_dir=None, *,
                 transport_factory=None, command_timeout=.5, max_bad_frames=1,
                 heartbeat_interval=.05, max_host_age_s=.1, record_capacity=1024):
        if type(rate_hz) is not int or rate_hz not in _RATE:
            raise ValidationError('rate must be 0, 100, 250, 500 or 1000 Hz')
        for value in (command_timeout, heartbeat_interval, max_host_age_s):
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValidationError('timeouts must be finite and positive')
        if heartbeat_interval > .1:
            raise ValidationError('heartbeat must be at most 100ms')
        if type(max_bad_frames) is not int or max_bad_frames < 1:
            raise ValidationError('max_bad_frames must be positive')
        if type(record_capacity) is not int or record_capacity < 1:
            raise ValidationError('record capacity must be positive')
        self.port = str(port)
        self.rate_hz = rate_hz
        self.log_dir = None if log_dir is None else Path(log_dir)
        self._factory = transport_factory or SerialTransport
        self._timeout = command_timeout
        self._heartbeat_interval = heartbeat_interval
        self._max_host_age_ns = min(int(max_host_age_s*1e9), 100_000_000)
        self._max_bad_frames = max_bad_frames
        self._bad_frames = 0
        self._condition = threading.Condition(threading.RLock())
        self._write_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._end = threading.Event()
        self._wake = threading.Event()
        self._transport = None
        self._thread = None
        self._connected = False
        self._closed = False
        self._closing = False
        self._handshake = False
        self._state = None
        self._info = None
        self._state_version = 0
        self._replies = deque(maxlen=32)
        self._history = OrderedDict()
        self._sequence = 0
        self._active = False
        self._calibrating = False
        self._calibration_cancelled = False
        self._deadline_ns = None
        self.error = None
        self.records = deque(maxlen=record_capacity)
        self.records_dropped = 0
        self._log_queue = queue.Queue(maxsize=record_capacity)
        self._log_end = threading.Event()
        self._logger = None
        self.log_path = None
        self._sid = secrets.randbelow(UINT32)+1
        self.session = Session(str(self._sid), f'teensy:{self._sid}')
        self.action_limits = ActionLimits(25., 50_000_000, 20_000_000)

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self):
        if self._closed or self._connected:
            raise RigError('Rig cannot reconnect; create a new stopped session')
        owner = str(Path(self.port).resolve())
        with _OWNERS_LOCK:
            if owner in _OWNERS:
                raise RigError('device already exclusively owned')
            _OWNERS.add(owner)
        self._owner = owner
        try:
            self._transport = self._factory(self.port)
            self._connected = True
            self._start_logger()
            self._record('session', session=asdict(self.session), protocol=2)
            self._thread = threading.Thread(target=self._io, name='cartpole-rig-io', daemon=True)
            self._thread.start()
            self._command('HELLO', reply='HELLO', allow_error=True)
            self._handshake = True
            self._command('RATE', self.rate_hz, allow_error=True)
            self._send(f'V2 STATUS {self._sid}')
            state = self._wait_state(timeout=self._timeout, allow_error=True)
            if state.enabled:
                raise RigError('HELLO did not establish a stopped session')
            return self
        except BaseException:
            self.close()
            raise

    @property
    def state(self) -> State:
        with self._condition:
            if self._state is None:
                raise RigError('no validated state received')
            return self._state

    def _require(self, *, allow_error=False):
        if not self._connected or self._closed:
            raise RigError('rig is not connected')
        if self.error is not None and not allow_error:
            raise RigError(f'latched rig error: {self.error}')

    def _send(self, payload):
        line = encode(payload)
        self._require(allow_error=True)
        try:
            with self._write_lock:
                if payload.startswith('V2 PING ') and self._closing:
                    return
                written = self._transport.write(line)
                if written != len(line):
                    raise RigError('short transport write')
        except Exception as exc:
            error = RigError(f'transport write failure: {exc}')
            self._latch(error)
            raise error from exc
        self._record('command', payload=payload)

    def _command(self, command, *args, reply='OK', allow_error=False, timeout_s=None):
        self._require(allow_error=allow_error)
        with self._command_lock:
            with self._condition:
                self._replies.clear()
            self._send(' '.join(map(str, ('V2', command, self._sid, *args))))
            deadline = time.monotonic()+(self._timeout if timeout_s is None else timeout_s)
            with self._condition:
                while True:
                    if command == 'CALIBRATE' and self._calibration_cancelled:
                        raise RigError('encoder calibration cancelled by STOP')
                    for response in self._replies:
                        if response[1] == 'ERR':
                            raise RigError(f'executor rejected {command}: {response[3]}')
                        if response[1] == reply and (reply in ('HELLO', 'INFO') or response[3] == command):
                            return
                    if self.error is not None and not allow_error:
                        raise RigError(f'latched rig error: {self.error}')
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)
            self._latch(RigError(f'{command} acknowledgement timeout'))
            raise RigError(f'{command} acknowledgement timeout')

    def _record(self, kind, **data):
        record = dict(type=kind, host_monotonic_ns=time.monotonic_ns(), **data)
        self.records.append(record)
        if self._logger is not None:
            try:
                self._log_queue.put_nowait(record)
            except queue.Full:
                self.records_dropped += 1

    def _start_logger(self):
        if self.log_dir is None:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f'rig-{time.time_ns()}-{self._sid}.jsonl'
        stream = self.log_path.open('x', encoding='utf-8')
        def write_records():
            try:
                with stream:
                    while not self._log_end.is_set() or not self._log_queue.empty():
                        try:
                            record = self._log_queue.get(timeout=.02)
                        except queue.Empty:
                            continue
                        stream.write(canonical_json(record)+'\n')
                        stream.flush()
            except Exception as exc:
                self._latch(RigError(f'recording failure: {exc}'))
        self._logger = threading.Thread(target=write_records, name='cartpole-rig-log', daemon=True)
        self._logger.start()

    def _emergency_stop(self):
        if self._transport is None:
            return
        try:
            self._send(f'V2 STOP {self._sid}')
        except Exception:
            try:
                with self._write_lock:
                    self._transport.write(b'stop\n')
            except Exception:
                pass
        self._active = False
        self._deadline_ns = None

    def _latch(self, exc):
        with self._condition:
            first = self.error is None
            if first:
                self.error = exc
            self._condition.notify_all()
        if first:
            self._record('error', reason=str(exc))
            self._emergency_stop()

    def _accept(self, payload, received_ns):
        parts = payload.split(' ')
        if not self._handshake and (len(parts)<3 or parts[0]!='V2' or parts[1] not in ('HELLO','ERR') or parts[2]!=str(self._sid)):
            self._record('negotiation_discard', payload=payload)
            return
        if len(parts) < 3 or parts[0] != 'V2' or uint32(parts[2]) != self._sid:
            raise ProtocolError('wrong session or reply header')
        if parts[1] == 'S':
            state = parse_state(payload, received_ns=received_ns)
            with self._condition:
                previous = self._state
                state = replace(state,
                    unwrapped_tick=unwrap32(state.tick, None if previous is None else previous.unwrapped_tick),
                    unwrapped_us=unwrap32(state.us, None if previous is None else previous.unwrapped_us))
                if previous is not None and previous.mode==13 and state.mode==0 and not state.enabled:
                    self._active=False
                    self._deadline_ns=None
                self._state = state
                self._state_version += 1
                self._history[state.unwrapped_tick] = state
                while len(self._history) > 64:
                    self._history.popitem(last=False)
                self._condition.notify_all()
            self._record('state', state=asdict(state))
            if state.fault:
                self._latch(RigError(f'executor fault {state.fault}'))
        elif parts[1] == 'INFO':
            info = parse_info(payload, received_ns=received_ns)
            with self._condition:
                self._info = info
                self._replies.append(parts)
                self._condition.notify_all()
            self._record('info', info=asdict(info))
        elif parts[1] == 'HELLO':
            if len(parts) != 5 or parts[3:] != ['1', '1000']:
                raise ProtocolError('unsupported protocol revision or control frequency')
            with self._condition:
                self._handshake = True
                self._replies.append(parts); self._condition.notify_all()
            self._record('reply', payload=payload)
        elif parts[1] in ('OK', 'ERR'):
            if len(parts) != 4 or not parts[3] or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', parts[3]) is None:
                raise ProtocolError('invalid acknowledgement')
            with self._condition:
                self._replies.append(parts); self._condition.notify_all()
            self._record('reply', payload=payload)
            if parts[1] == 'ERR':
                self._latch(RigError(f'executor error: {parts[3]}'))
        else:
            raise ProtocolError('unknown reply')

    def _io(self):
        buffer = LineBuffer()
        next_ping = time.monotonic()+self._heartbeat_interval
        while not self._end.is_set():
            try:
                data = self._transport.read(512)
                if data:
                    for line in buffer.feed(data, raise_overflow=self._handshake):
                        try:
                            self._accept(decode(line), time.monotonic_ns())
                        except ProtocolError as exc:
                            if self._handshake:
                                raise
                            self._record('negotiation_discard', reason=str(exc))
                    self._bad_frames = 0
                now = time.monotonic()
                if self._handshake and not self._closing and self.error is None and now >= next_ping:
                    self._send(f'V2 PING {self._sid}')
                    next_ping = now+self._heartbeat_interval
                if self._active and self.error is None:
                    state = self._state
                    if state is not None and time.monotonic_ns()-state.received_ns > self._max_host_age_ns:
                        self._latch(RigError('stale host telemetry'))
                    elif self._deadline_ns is not None and time.monotonic_ns() >= self._deadline_ns:
                        self._emergency_stop()
                        self._record('duration_end')
                # Event.wait is interruptible; no busy heartbeat loop on empty transports.
                if not data:
                    self._wake.wait(.001)
                    self._wake.clear()
            except ProtocolError as exc:
                self._bad_frames += 1
                self._record('bad_frame', reason=str(exc))
                if self._bad_frames >= self._max_bad_frames:
                    self._latch(exc)
            except Exception as exc:
                if not self._end.is_set():
                    self._latch(RigError(f'transport failure: {exc}'))
                return

    def wait_state(self, after_tick=None, timeout=1) -> State:
        return self._wait_state(after_tick, timeout)

    def _wait_state(self, after_tick=None, timeout=1, *, allow_error=False) -> State:
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValidationError('state timeout must be positive')
        if after_tick is not None and (type(after_tick) is not int or after_tick < 0):
            raise ValidationError('after_tick must be a nonnegative integer')
        deadline = time.monotonic()+timeout
        with self._condition:
            while True:
                self._require(allow_error=allow_error)
                state = self._state
                if state is not None and (after_tick is None or (
                    state.unwrapped_tick > after_tick if after_tick > UINT32 else
                    0 < ((state.tick-after_tick)&UINT32) < 0x80000000)):
                    return state
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('no newer validated state')
                self._condition.wait(remaining)

    def _fresh(self, state):
        age = time.monotonic_ns()-state.received_ns
        if age < 0 or age > self._max_host_age_ns:
            raise ValidationError('stale host receipt')
        return age

    def _observation(self, state):
        timestamp = state.unwrapped_us*1000
        healthy = bool(state.flags & 1)
        def sample(entity, quantity, source, value, unit, method, kind, valid=True, reason='encoder unhealthy'):
            return Sample(entity, quantity, source, value if valid else None, unit,
                          'encoder-zero' if source == 'magnetic' else 'cart-step-home',
                          method, 'valid' if valid else 'invalid',
                          None if valid else reason, kind,
                          timestamp, timestamp, timestamp)
        return Observation(self.session.session_id, self.session.clock_id, state.unwrapped_tick,
            timestamp, 'board acquisition snapshot proxy', (
                sample('pole','angle','magnetic',state.theta,'rad','magnetic_decoded','measured',healthy),
                sample('pole','angular_velocity','magnetic',state.omega,'rad/s','filtered_magnetic_rate','estimated',healthy),
                sample('cart','position','step',state.x,'m','step_count','estimated',state.homed,'cart physical reference unknown'),
                sample('cart','velocity','step',state.velocity,'m/s','commanded_velocity','estimated')))

    def observation(self) -> Observation:
        self._require()
        state = self.state
        self._fresh(state)
        return self._observation(state)

    def _stopped_healthy(self):
        self._require()
        state = self.state
        if time.monotonic_ns()-state.received_ns>self._max_host_age_ns:
            state=self._snapshot()
        self._fresh(state)
        if self._calibrating or state.flags & 256:
            raise RigError('encoder calibration is in progress; wait or stop to cancel')
        if state.enabled or state.mode != 0 or not state.healthy:
            raise RigError('operation requires stopped healthy executor')
        return state

    def _snapshot(self, *, allow_error=False):
        self._require(allow_error=allow_error)
        with self._condition:
            version=self._state_version
        self._send(f'V2 STATUS {self._sid}')
        deadline=time.monotonic()+self._timeout
        with self._condition:
            while self._state_version<=version:
                self._require(allow_error=allow_error)
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise RigError('STATUS state timeout')
                self._condition.wait(remaining)
            return self._state

    def _command_state(self, command, *args, predicate, allow_error=False):
        # Observe state publications after the command, including same-control-tick snapshots.
        with self._condition:
            version = self._state_version
        self._command(command, *args, allow_error=allow_error)
        self._snapshot(allow_error=allow_error)
        deadline = time.monotonic()+self._timeout
        with self._condition:
            while self._state_version <= version or not predicate(self._state):
                self._require(allow_error=allow_error)
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    self._latch(RigError(f'{command} state confirmation timeout'))
                    raise RigError(f'{command} state confirmation timeout')
                self._condition.wait(remaining)

    def center(self):
        """Operator asserts the cart is physically centered now; no motion routine."""
        state = self._stopped_healthy()
        if state.switch_profile:
            raise RigError('CENTER requires explicit no-switch commissioning profile')
        self._command_state('CENTER', predicate=lambda s:s.homed)

    def calibrate_encoder(self, pose='upright'):
        """Capture and save the magnetic reference from a stationary known pose.

        Hold the pole straight up for ``upright`` or let it hang fully down for
        ``hanging``. The board acknowledges only after its stable capture and
        EEPROM verification finish. No motion, home, switch or fault change is
        requested. Ctrl-C or any failure requests STOP to cancel capture.
        """
        if pose not in ('upright', 'hanging'):
            raise ValidationError('encoder calibration pose must be upright or hanging')
        self._stopped_healthy()
        if self.get_info().firmware not in ('executor-v2-cart2', 'executor-v3-encguard'):
            raise RigError('update firmware to executor-v2-cart2 or executor-v3-encguard before encoder calibration')
        with self._condition:
            self._stopped_healthy()
            self._calibrating = True
            self._calibration_cancelled = False
        try:
            # Firmware has a 5 s capture deadline; ordinary commands retain
            # their shorter transport timeout.
            self._command('CALIBRATE', pose, timeout_s=6.)
            state = self._snapshot()
            if state.enabled or state.mode != 0 or not state.healthy or state.flags & 256:
                raise RigError('calibration did not confirm a stopped healthy executor')
            info = self.get_info()
            if not info.reference_saved:
                raise RigError('encoder calibration was not confirmed saved')
            with self._condition:
                if self._calibration_cancelled:
                    raise RigError('encoder calibration cancelled by STOP')
            return info
        except BaseException:
            self._emergency_stop()
            raise
        finally:
            with self._condition:
                self._calibrating = False
                self._condition.notify_all()

    def configure_switches(self, enabled: bool):
        if type(enabled) is not bool:
            raise ValidationError('switch profile selection must be bool')
        self._stopped_healthy()
        self._command_state('SWITCHES', int(enabled), predicate=lambda s:s.switch_profile == enabled)

    def home(self):
        if self.rate_hz==0:
            raise RigError('homing requires streaming telemetry; set a positive rate')
        state = self._stopped_healthy()
        if not state.switch_profile:
            raise RigError('HOME requires enabled physical switch profile')
        self._active=True
        self._deadline_ns=None
        try:
            self._command_state('HOME', predicate=lambda s:s.mode==13 or (s.homed and not s.enabled))
        except BaseException:
            self._emergency_stop()
            raise

    def _duration(self, duration_s):
        if type(duration_s) not in (int,float) or not math.isfinite(duration_s):
            raise ValidationError('duration must be finite')
        milliseconds = math.floor(duration_s*1000)
        if not 1 <= milliseconds <= 60000:
            raise ValidationError('duration must be 1ms..60s')
        return milliseconds

    def _start(self, command, args, duration_s, predicate):
        if self.rate_hz==0:
            raise RigError('motion requires streaming telemetry; set a positive rate')
        duration = self._duration(duration_s)
        state = self._stopped_healthy()
        if not state.homed:
            raise RigError('motion requires a physical home or explicit centering')
        # Set active before write so parse/read failures during ACK always stop.
        self._active = True
        self._deadline_ns = time.monotonic_ns()+duration*1_000_000
        try:
            self._command_state(command,*args,duration,predicate=predicate)
            self._sequence = 0
        except BaseException:
            self._emergency_stop()
            raise

    def start(self, mode='auto', duration_s=10):
        """Select the preserved controller on the board (auto/bal/manual)."""
        if mode not in ('auto','bal','manual'):
            raise ValidationError('mode must be auto, bal or manual')
        self._start('MODE',(mode,),duration_s,lambda s:s.enabled and s.mode !=12)

    def arm(self, duration_s=10):
        """Explicitly arm external acceleration; first action due within 20 ticks."""
        self._start('ARM',(),duration_s,lambda s:s.enabled and s.mode==12)

    def _intent(self, command, value, ttl_ms, mode, bound):
        self._require()
        if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>bound:
            raise ValidationError('intent is nonfinite or exceeds bound')
        if type(ttl_ms) is not int or not 1<=ttl_ms<=50:
            raise ValidationError('TTL must be 1..50 integer milliseconds')
        state = self.state
        age = self._fresh(state)
        if not state.enabled or state.mode !=mode or not state.healthy:
            raise RigError('intent requires the matching active healthy mode')
        # Conservative ceil avoids extending an action using a stale board snapshot.
        age_ticks = (age+_NS_TICK-1)//_NS_TICK
        if age_ticks>20 or age_ticks>=ttl_ms:
            raise ValidationError('observed board tick is too old or lease has expired')
        sequence = self._sequence+1
        if sequence>UINT32:
            raise ValidationError('action sequence exhausted; stop before a new lease')
        self._send(f'V2 {command} {self._sid} {sequence} {state.tick} {ttl_ms} {value:.9g}')
        self._sequence = sequence
        return sequence

    def set_acceleration(self, value, ttl_ms=20):
        return self._intent('A',value,ttl_ms,12,25.)

    def set_velocity(self, value, ttl_ms=50):
        return self._intent('V',value,ttl_ms,1,.15)

    def step(self, request: ActionRequest | None) -> Observation:
        """Validate a board-clock request before any write; never implicitly arm.

        The request expiry is anchored to the observed board snapshot, not the
        host issue time. ``None`` publishes the latest observation only.
        """
        self._require()
        if request is None:
            return self.observation()
        if not isinstance(request,ActionRequest):
            raise ValidationError('expected ActionRequest or None')
        latest = self.state
        age = self._fresh(latest)
        observed = self._history.get(request.observation_sequence)
        if observed is None:
            raise ValidationError('unknown or retired observation sequence')
        observation = self._observation(observed)
        now_ns = latest.unwrapped_us*1000+age
        validate_action(request,observation,self.action_limits,now_ns=now_ns,
                        previous_sequence=self._sequence)
        if not 1<=request.sequence<=UINT32:
            raise ValidationError('action sequence must fit nonzero uint32')
        if not latest.enabled or latest.mode!=12 or not latest.healthy:
            raise RigError('action requires explicit external arm')
        ticks = latest.unwrapped_tick-observed.unwrapped_tick+(age+_NS_TICK-1)//_NS_TICK
        ttl = (request.expires_at_ns-observation.available_ns)//_NS_TICK
        if ticks>20 or not 1<=ttl<=50 or ticks>=ttl:
            raise ValidationError('observed tick age or anchored TTL invalid')
        self._send(f'V2 A {self._sid} {request.sequence} {observed.tick} {ttl} {request.acceleration_m_s2:.9g}')
        self._sequence = request.sequence
        self._record('action_request', request=asdict(request))
        return self.observation()

    def stop(self):
        self._require(allow_error=True)
        with self._condition:
            if self._calibrating:
                # Wake the deferred ACK wait before taking the command lock.
                # Its exception path sends STOP without waiting for an ACK.
                self._calibration_cancelled = True
                self._condition.notify_all()
        self._command_state('STOP',predicate=lambda s:not s.enabled and s.mode in (0,4),allow_error=True)
        self._active = False
        self._deadline_ns = None

    def clear_fault(self):
        self._require(allow_error=True)
        state=self.state
        if time.monotonic_ns()-state.received_ns>self._max_host_age_ns:
            state=self._snapshot(allow_error=True)
        if state.enabled or state.mode not in (0,4):
            raise RigError('fault clear requires stopped executor')
        self._command_state('CLEAR',predicate=lambda s:s.fault==0 and not s.enabled,allow_error=True)
        with self._condition:
            self.error=None
            self._bad_frames=0
            self._condition.notify_all()

    def get_info(self):
        """Read actual firmware calibration and homing metadata while stopped.

        This remains available for fault diagnosis and never changes EEPROM,
        coordinates, switch configuration or driver enable.
        """
        self._require(allow_error=True)
        if self.state.enabled or self._active:
            raise RigError('firmware diagnostics require stopped executor')
        self._command('INFO', reply='INFO', allow_error=True)
        return self._info

    def set_rate(self, hz):
        if type(hz) is not int or hz not in _RATE:
            raise ValidationError('rate must be 0, 100, 250, 500 or 1000 Hz')
        self._command('RATE',hz)
        self.rate_hz=hz

    def close(self):
        if self._closed:
            return
        self._closing = True
        if self._connected:
            try:
                self.stop()
            except Exception:
                self._emergency_stop()
        self._end.set(); self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(self._timeout+.1)
        if self._transport is not None:
            self._transport.close()
        self._record('termination',error=None if self.error is None else str(self.error),
                     records_dropped=self.records_dropped)
        self._log_end.set()
        if self._logger is not None:
            self._logger.join(self._timeout+.1)
        self._connected=False; self._closed=True
        if hasattr(self,'_owner'):
            with _OWNERS_LOCK:
                _OWNERS.discard(self._owner)

RealRig = Rig
