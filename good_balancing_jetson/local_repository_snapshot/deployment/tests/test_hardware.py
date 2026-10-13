import socket
import threading
import time
import unittest

from cartpole_deploy.hardware import HardwareRig
from cartpole_deploy.protocol import ProtocolError, DeviceError, TransportError, encode_frame, decode_frame

STATE = 'D1 S {time_us} {mode} 0.2 -1 0.01 0.02 0.03 100 {flags} {seq} {session} none'
INFO = 'D1 I 1 1000 500 60 26666.666667 0.15 0.25 2 20 encoder'


class LoopbackServer:
    def __init__(self, handler=None):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.received = []
        self.errors = []
        self.handler = handler
        self.session = 0
        self.seq = 0
        self.flags = 1
        self.mode = 'DISARMED'
        self.start = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            conn, _ = self.listener.accept()
            self.conn = conn
            conn.settimeout(1)
            with conn, conn.makefile('rb') as reader:
                while line := reader.readline():
                    request = decode_frame(line)
                    self.received.append(request)
                    if self.handler is not None and self.handler(self, conn, request):
                        continue
                    verb = request.split()[1]
                    if verb == 'info':
                        response = INFO
                    elif verb == 'state':
                        response = STATE.format(time_us=int((time.monotonic()-self.start)*1e6), mode=self.mode, flags=self.flags, seq=self.seq, session=self.session)
                    else:
                        if verb == 'home':
                            self.flags |= 2
                        elif verb == 'arm':
                            self.session = int(request.split()[2]); self.mode = 'ARMED'; self.flags |= 4
                        elif verb == 'act':
                            self.seq = int(request.split()[3]); self.mode = 'RUNNING'
                        elif verb in ('stop', 'clear'):
                            self.flags = 1; self.mode = 'DISARMED'; self.session = 0
                        response = 'D1 OK ' + verb
                    conn.sendall(encode_frame(response))
        except (ConnectionError, socket.timeout):
            pass
        except Exception as exc:
            self.errors.append(exc)
        finally:
            self.listener.close()

    def close(self):
        if hasattr(self, 'conn'):
            try: self.conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        self.listener.close()
        self.thread.join(2)
        if self.errors:
            raise self.errors[0]


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.close()

    def rig(self, handler=None, timeout=.15):
        server = LoopbackServer(handler)
        self.servers.append(server)
        return server, HardwareRig('127.0.0.1', server.port, timeout=timeout)

    def test_readonly_context_never_enables_or_stops(self):
        server, rig = self.rig()
        with rig:
            state = rig.read()
            self.assertEqual(state.mode, 'DISARMED')
            self.assertFalse(rig.capabilities()['imu'])
            self.assertEqual(rig.capabilities()['position_source'], 'commanded_steps')
        self.assertEqual(server.received, ['D1 info', 'D1 state'])

    def test_fragmented_state_and_interleaved_stream(self):
        def handler(server, conn, request):
            if request == 'D1 state':
                payload = STATE.format(time_us=123, mode='DISARMED', flags=1, seq=0, session=0)
                frame = encode_frame(payload)
                for index in range(0, len(frame), 3):
                    conn.sendall(frame[index:index+3])
                return True
            if request == 'D1 home 0.1':
                stream = STATE.format(time_us=124, mode='DISARMED', flags=3, seq=0, session=0)
                conn.sendall(encode_frame(stream) + encode_frame('D1 OK home'))
                server.flags = 3
                return True
            return False
        _, rig = self.rig(handler)
        with rig:
            self.assertEqual(rig.read().time_us, 123)
            rig.home(.1)

    def test_owned_armed_context_stops_and_increasing_sequence(self):
        server, rig = self.rig()
        with rig:
            rig.home(.1)
            rig.arm(123)
            rig.command('acceleration', .1, ttl_ms=100)
            rig.command('velocity', .01, ttl_ms=100)
        acts = [r.split() for r in server.received if r.startswith('D1 act')]
        self.assertEqual([int(a[3]) for a in acts], [1, 2])
        self.assertEqual([a[2] for a in acts], ['123', '123'])
        self.assertEqual(server.received[-1], 'D1 stop')

    def test_rejection_propagates_and_is_not_retried(self):
        def handler(server, conn, request):
            if request.startswith('D1 act'):
                conn.sendall(encode_frame('D1 ERR STALE'))
                return True
            return False
        server, rig = self.rig(handler)
        with rig:
            rig.home(.1); rig.arm(12)
            with self.assertRaises(DeviceError) as exc:
                rig.command('acceleration', .1)
            self.assertEqual(exc.exception.code, 'STALE')
        self.assertEqual(len([r for r in server.received if r.startswith('D1 act')]), 1)

    def test_bad_crc_closes_transport(self):
        def handler(server, conn, request):
            if request == 'D1 state':
                conn.sendall(b'@D1 OK state*0000\n')
                return True
            return False
        _, rig = self.rig(handler)
        with self.assertRaises(ProtocolError):
            rig.read()
        with self.assertRaises(TransportError):
            rig.read()
        rig.close()

    def test_timeout_no_retry_and_close_is_idempotent(self):
        def handler(server, conn, request):
            return request == 'D1 state'
        server, rig = self.rig(handler, timeout=.04)
        started = time.monotonic()
        with self.assertRaises(TransportError): rig.read()
        self.assertLess(time.monotonic()-started, .2)
        rig.close(); rig.close()
        self.assertEqual(server.received.count('D1 state'), 1)

    def test_client_argument_validation_and_no_unarmed_actions(self):
        server, rig = self.rig()
        with rig:
            with self.assertRaises(ValueError): rig.command('acceleration', .1)
            for value in [float('nan'), float('inf'), .16, -.01]:
                with self.assertRaises(ValueError): rig.home(value)
            for hz in [-1, 501, .5, True]:
                with self.assertRaises(ValueError): rig.set_stream_rate(hz)
        self.assertEqual(server.received, ['D1 info'])

    def test_action_deadline_includes_state_roundtrip(self):
        def handler(server, conn, request):
            if request == 'D1 state' and server.mode == 'ARMED':
                time.sleep(.07)
            return False
        server, rig = self.rig(handler)
        with rig:
            rig.home(.1); rig.arm(55)
            with self.assertRaises(TransportError): rig.command('acceleration', .1, ttl_ms=20)
        self.assertFalse(any(r.startswith('D1 act') for r in server.received))

    def test_state_ack_without_sample_is_rejected(self):
        def handler(server, conn, request):
            if request == 'D1 state':
                conn.sendall(encode_frame('D1 OK state'))
                return True
            return False
        _, rig = self.rig(handler)
        with rig:
            with self.assertRaises(ProtocolError): rig.read()

    def test_stream_iteration_sends_no_heartbeat_or_action(self):
        def handler(server, conn, request):
            if request == 'D1 stream 100':
                sample = STATE.format(time_us=1, mode='DISARMED', flags=1, seq=0, session=0)
                conn.sendall(encode_frame('D1 OK stream') + encode_frame(sample))
                return True
            return False
        server, rig = self.rig(handler)
        with rig:
            rig.set_stream_rate(100)
            self.assertEqual(next(rig.iter_observations()).time_us, 1)
            rig.set_stream_rate(0)
        self.assertEqual(server.received, ['D1 info', 'D1 stream 100', 'D1 stream 0'])

    def test_timestamp_wrap_allowed_but_rollback_rejected(self):
        values = iter([4294967290, 4, 3])
        def handler(server, conn, request):
            if request == 'D1 state':
                sample = STATE.format(time_us=next(values), mode='DISARMED', flags=1, seq=0, session=0)
                conn.sendall(encode_frame(sample))
                return True
            return False
        _, rig = self.rig(handler)
        with rig:
            self.assertEqual(rig.read().time_us, 4294967290)
            self.assertEqual(rig.read().time_us, 4)
            with self.assertRaises(ProtocolError): rig.read()

    def test_peer_close_is_transport_error(self):
        def handler(server, conn, request):
            if request == 'D1 state':
                conn.shutdown(socket.SHUT_RDWR)
                return True
            return False
        _, rig = self.rig(handler)
        with rig:
            with self.assertRaises(TransportError): rig.read()

    def test_action_ack_after_ttl_is_uncertain_without_retry(self):
        def handler(server, conn, request):
            if request.startswith('D1 act'):
                time.sleep(.04)
                conn.sendall(encode_frame('D1 OK act'))
                return True
            return False
        server, rig = self.rig(handler)
        with rig:
            rig.home(.1); rig.arm(81)
            with self.assertRaises(TransportError): rig.command('acceleration', .1, ttl_ms=20)
        self.assertEqual(len([r for r in server.received if r.startswith('D1 act')]), 1)

    def test_old_session_cannot_be_reused_after_stop(self):
        _, rig = self.rig()
        with rig:
            rig.home(.1); rig.arm(82); rig.stop(); rig.home(.1)
            with self.assertRaises(ValueError): rig.arm(82)

    def test_position_target_respects_asserted_home_span_margin(self):
        server, rig = self.rig()
        with rig:
            rig.home(.1); rig.arm(83)
            with self.assertRaises(ValueError): rig.command('position', .09)
        self.assertFalse(any(r.startswith('D1 act') for r in server.received))

    def test_rejected_arm_does_not_acquire_close_stop_ownership(self):
        def handler(server, conn, request):
            if request.startswith('D1 arm'):
                conn.sendall(encode_frame('D1 ERR session'))
                return True
            return False
        server, rig = self.rig(handler)
        with rig:
            rig.home(.1)
            with self.assertRaises(DeviceError): rig.arm(94)
        self.assertNotIn('D1 stop', server.received)

    def test_arm_ack_is_bounded_by_initial_arm_lease(self):
        def handler(server, conn, request):
            if request.startswith('D1 arm'):
                time.sleep(.13)
                conn.sendall(encode_frame('D1 OK arm'))
                return True
            return False
        _, rig = self.rig(handler, timeout=.3)
        with rig:
            rig.home(.1)
            started = time.monotonic()
            with self.assertRaises(TransportError): rig.arm(95)
            self.assertLess(time.monotonic()-started, .125)

    def test_wrong_optional_ack_sequence_rejected(self):
        def handler(server, conn, request):
            if request.startswith('D1 act'):
                conn.sendall(encode_frame('D1 OK act 999'))
                return True
            return False
        _, rig = self.rig(handler)
        with rig:
            rig.home(.1); rig.arm(42)
            with self.assertRaises(ProtocolError): rig.command('velocity', 0, ttl_ms=100)


if __name__ == '__main__':
    unittest.main()
