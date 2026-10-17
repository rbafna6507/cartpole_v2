"""Passive recording completion is explicit, bounded, and failure preserving."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading
import time
from unittest.mock import patch

import pytest

from cartpole_sdk.identification import experiments as probe
from test_passive_collection_baseline import camera_reader
from test_system_id_experiments import scripted_rig


@contextmanager
def scripted_recording():
    rig, clock = scripted_rig()
    with patch('cartpole_sdk.rig.client.time', clock), patch.object(probe, 'time', clock):
        yield rig, clock


def assert_no_motion(rig):
    assert not rig.state.enabled
    assert rig.commands[-1][1] == 'STOP'
    assert not any(c[1] in ('ARM', 'MODE', 'HOME', 'REHOME', 'CLEAR', 'CALIBRATE', 'SET', 'A') for c in rig.commands)


def test_done_finishes_after_baseline_and_binds_actual_duration_to_raw_event():
    with scripted_recording() as (rig, clock):
        calls = []
        def done():
            calls.append(clock.now_ns)
            return clock.now_ns >= 2_250_000_000
        result = probe.run_passive(rig, seconds=30., camera_read=camera_reader(clock), finish_requested=done)
    assert calls[0] >= 2_000_000_000
    assert result['requested_seconds'] == 30.
    assert result['elapsed_seconds'] == pytest.approx(.25)
    assert result['finish_reason'] == 'operator_done'
    event = next(r for r in rig.records if r['type'] == 'passive_finish')
    for key in ('requested_seconds', 'elapsed_seconds', 'finish_reason'):
        assert event[key] == result[key]
    assert not any(r['type'] == 'passive_failure' for r in rig.records)
    assert_no_motion(rig)


def test_duration_completion_reports_actual_elapsed_time():
    with scripted_recording() as (rig, clock):
        result = probe.run_passive(rig, seconds=1., camera_read=camera_reader(clock))
    assert result['requested_seconds'] == 1.
    assert result['elapsed_seconds'] == pytest.approx(1.)
    assert result['finish_reason'] == 'duration_elapsed'
    assert_no_motion(rig)


def test_sigint_while_waiting_is_graceful_and_restores_signal_handler():
    previous_handler = signal.getsignal(signal.SIGINT)
    with scripted_recording() as (rig, clock):
        original = rig.wait_state
        def wait(*args, **kwargs):
            state = original(*args, **kwargs)
            if clock.now_ns == 2_250_000_000:
                os.kill(os.getpid(), signal.SIGINT)
            return state
        rig.wait_state = wait
        try:
            result = probe.run_passive(rig, seconds=30., camera_read=camera_reader(clock))
        except KeyboardInterrupt:
            pytest.fail('recording SIGINT escaped instead of requesting graceful finish')
    assert signal.getsignal(signal.SIGINT) is previous_handler
    assert result['finish_reason'] == 'keyboard_interrupt'
    assert result['elapsed_seconds'] == pytest.approx(.25)
    assert not any(r['type'] == 'passive_failure' for r in rig.records)
    assert_no_motion(rig)


@pytest.mark.parametrize('failure', ('wait', 'health', 'camera', 'stop', 'second_interrupt'))
def test_finish_request_cannot_hide_later_collection_failure(failure):
    with scripted_recording() as (rig, clock):
        original_wait, original_stop = rig.wait_state, rig.stop
        def wait(*args, **kwargs):
            state = original_wait(*args, **kwargs)
            if clock.now_ns == 2_250_000_000:
                os.kill(os.getpid(), signal.SIGINT)
                if failure == 'wait':
                    raise TimeoutError('injected no newer state')
                if failure == 'health':
                    rig._state = replace(state, flags=state.flags & ~4)
                if failure == 'second_interrupt':
                    os.kill(os.getpid(), signal.SIGINT)
            return rig.state
        def stop():
            original_stop()
            if failure == 'stop' and clock.now_ns >= 2_250_000_000:
                raise RuntimeError('injected stop failure')
        def check():
            if failure == 'camera' and clock.now_ns >= 2_250_000_000:
                raise RuntimeError('injected camera failure')
        rig.wait_state, rig.stop = wait, stop
        with pytest.raises(BaseException) as caught:
            probe.run_passive(rig, seconds=30., camera_read=camera_reader(clock), check=check)
    if failure == 'second_interrupt':
        assert isinstance(caught.value, KeyboardInterrupt)
    else:
        assert not isinstance(caught.value, KeyboardInterrupt)
    assert any(r['type'] in ('passive_failure', 'stop_failure') for r in rig.records)
    assert_no_motion(rig)


def test_terminal_done_poll_does_not_block_on_partial_line_or_finish_on_eof():
    from cartpole_sdk.identification.finish import TerminalFinish
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, 'r') as source:
            finish = TerminalFinish(source)
            assert finish() is False
            os.write(write_fd, b'do')
            assert finish() is False
            os.write(write_fd, b'ne')
            assert finish() is False
            os.close(write_fd); write_fd = None
            assert finish() is False
            assert finish() is False
    finally:
        if write_fd is not None:
            os.close(write_fd)


def test_terminal_done_requires_complete_explicit_command():
    from cartpole_sdk.identification.finish import TerminalFinish
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, 'r') as source:
            finish = TerminalFinish(source)
            os.write(write_fd, b'not done\n')
            assert finish() is False
            os.write(write_fd, b' done \n')
            assert finish() is True
    finally:
        os.close(write_fd)


class CameraHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        if self.path == '/api/clock':
            self.wfile.write(json.dumps({'monotonic_s': time.monotonic()}).encode())
            return
        try:
            for sequence in range(1000):
                stamp = time.monotonic()
                row = dict(schema='cartpole-sensing-stream-v1', stream_seq=sequence, host_t=stamp,
                           vision=dict(seq=sequence, t=stamp, stale=False, age_since_host_read_s=0., worker_error=None))
                self.wfile.write((json.dumps(row) + '\n').encode())
                self.wfile.flush()
                time.sleep(.01)
        except (BrokenPipeError, ConnectionResetError):
            pass


def test_actual_spawned_camera_worker_ignores_sigint_and_closes_cleanly(tmp_path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), CameraHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    recorder = probe.CameraRecorder(f'http://127.0.0.1:{server.server_port}/stream', tmp_path, 10.)
    try:
        recorder.start()
        before = signal.getsignal(signal.SIGINT)
        os.kill(recorder.process.pid, signal.SIGINT)
        time.sleep(.1)
        recorder.check()
        report = recorder.close()
        assert 'failure' not in report
        assert report['frames'] > 1
        assert 'end' in report['clock_sync']
        assert signal.getsignal(signal.SIGINT) is before
    finally:
        if recorder.process.is_alive():
            recorder.close()
        server.shutdown()
        server.server_close()
        thread.join(2.)


@pytest.mark.parametrize('camera_failure', (False, True))
def test_collection_report_retains_baseline_and_finish_metadata_but_camera_failure_still_fails(tmp_path, camera_failure):
    with scripted_recording() as (rig, clock):
        class Camera:
            def __init__(self, *_):
                pass
            def start(self):
                pass
            def check(self):
                pass
            def latest(self):
                return camera_reader(clock)()
            def close(self):
                return {'failure': 'injected camera close failure'} if camera_failure else {'frames': 100}
        options = dict(output=tmp_path/'run', port='offline', seconds=30.,
                       rig_factory=lambda *args, **kwargs: rig, camera_factory=Camera,
                       finish_requested=lambda: clock.now_ns >= 2_250_000_000)
        if camera_failure:
            with pytest.raises(RuntimeError, match='camera close failure'):
                probe.collect('passive', **options)
        else:
            probe.collect('passive', **options)
    report = json.loads((tmp_path/'run'/'report.json').read_text())
    assert report['completed'] is (not camera_failure)
    assert report['stop_confirmed'] is True
    assert report['result']['baseline']['schema'] == 'cartpole-passive-baseline-v1'
    assert report['result']['finish_reason'] == 'operator_done'
    assert report['result']['elapsed_seconds'] == pytest.approx(.25)
    if camera_failure:
        assert 'camera close failure' in report['failure']
    else:
        assert 'failure' not in report
    assert_no_motion(rig)


def test_cli_wires_done_reader_and_prints_finish_instruction(tmp_path, capsys):
    from cartpole_sdk.identification import cli
    read_fd, write_fd = os.pipe()
    def collect(kind, **options):
        assert kind == 'passive'
        options['ready'](dict(status='recording', seconds=30.,
                             instruction='Type done then Enter to finish. Maximum duration: 30 seconds.'))
        os.write(write_fd, b'done\n')
        assert options['finish_requested']() is True
        return dict(completed=True, stop_confirmed=True,
                    result=dict(finish_reason='operator_done', elapsed_seconds=.25, requested_seconds=30.))
    try:
        with os.fdopen(read_fd, 'r') as source, patch.object(cli.sys, 'stdin', source), patch.object(probe, 'collect', collect):
            code = cli.main(['collect-passive', '--port', 'offline', '--seconds', '30', '--output', str(tmp_path/'run')])
    finally:
        os.close(write_fd)
    output = capsys.readouterr().out
    assert code == 0
    assert 'Type done then Enter' in output
    final = json.loads(output.splitlines()[-1])
    assert final['finish_reason'] == 'operator_done'
    assert final['elapsed_seconds'] == .25
    assert final['requested_seconds'] == 30.


def test_recovery_cli_has_no_output_requirement_and_reports_sidecar(tmp_path, capsys):
    from cartpole_sdk.identification import cli
    cli.parser().parse_args(['recover-passive', '--input', 'rig.jsonl', '--reason', 'operator interrupt'])
    from cartpole_sdk.identification import interruption_recovery
    source = tmp_path/'rig.jsonl'
    def recover(value, *, reason):
        assert value == str(source)
        assert reason == 'Operator pressed Ctrl-C after releases settled'
        return tmp_path/'recovery.json'
    with patch.object(interruption_recovery, 'recover_passive', recover):
        code = cli.main(['recover-passive', '--input', str(source), '--reason', 'Operator pressed Ctrl-C after releases settled'])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output['recovery'] == str(tmp_path/'recovery.json')
    assert output['status'] == 'recovered_for_review'


def test_progress_output_delay_checks_latest_telemetry_instead_of_stale_baseline_snapshot():
    with scripted_recording() as (rig, clock):
        rig._max_host_age_ns = 20_000_000  # collect() uses max_host_age_s=.02.
        def ready(event):
            # Real serial reception continues while terminal output is busy.
            if event['status'] in ('recording', 'angles'):
                for _ in range(3):
                    rig.wait_state(after_tick=rig.state.unwrapped_tick)
        result = probe.run_passive(rig, seconds=1., camera_read=camera_reader(clock), ready=ready)
    assert result['finish_reason'] == 'duration_elapsed'
    assert_no_motion(rig)


@pytest.mark.parametrize('finish_mode', ('done', 'duration', 'sigint'))
def test_passive_finish_rejects_frozen_camera_even_while_worker_is_alive(finish_mode):
    from cartpole_sdk.contracts import ValidationError
    with scripted_recording() as (rig, clock):
        read = camera_reader(clock)
        frozen = None
        def camera():
            nonlocal frozen
            if clock.now_ns <= 2_000_000_000:
                frozen = read()
            return frozen
        def finish():
            if clock.now_ns >= 2_300_000_000 and finish_mode == 'sigint':
                os.kill(os.getpid(), signal.SIGINT)
            return clock.now_ns >= 2_300_000_000 and finish_mode == 'done'
        with pytest.raises(ValidationError, match='camera'):
            probe.run_passive(rig, seconds=1., camera_read=camera, check=lambda: None,
                              finish_requested=finish)
    assert any(row['type'] == 'passive_failure' for row in rig.records)
    assert not any(row['type'] == 'passive_finish' for row in rig.records)
    assert_no_motion(rig)


@pytest.mark.parametrize('bad_sample', ('missing', 'old_source', 'future_receipt', 'future_source',
                                       'receipt_plus_source_age', 'stale', 'worker_error', 'missing_age'))
def test_passive_finish_validates_source_and_local_receipt_age(bad_sample):
    from cartpole_sdk.contracts import ValidationError
    with scripted_recording() as (rig, clock):
        read = camera_reader(clock)
        def camera():
            sample = read()
            if clock.now_ns <= 2_000_000_000:
                return sample
            sample['vision']['age_since_host_read_s'] = .01
            if bad_sample == 'missing':
                return None
            if bad_sample == 'old_source':
                sample['vision']['t'] -= .2
                sample['vision']['age_since_host_read_s'] = .21
            if bad_sample == 'future_receipt':
                sample['collector_received_ns'] = clock.now_ns + 1
            if bad_sample == 'future_source':
                sample['vision']['t'] = sample['host_t'] + .1
            if bad_sample == 'receipt_plus_source_age':
                sample['collector_received_ns'] = clock.now_ns - 100_000_000
                sample['vision']['t'] = sample['host_t'] - .1
                sample['vision']['age_since_host_read_s'] = .1
            if bad_sample == 'stale':
                sample['vision']['stale'] = True
            if bad_sample == 'worker_error':
                sample['vision']['worker_error'] = 'capture failed'
            if bad_sample == 'missing_age':
                sample['vision'].pop('age_since_host_read_s')
            return sample
        with pytest.raises(ValidationError, match='camera'):
            probe.run_passive(rig, seconds=1., camera_read=camera, check=lambda: None,
                              finish_requested=lambda: clock.now_ns >= 2_300_000_000)
    assert_no_motion(rig)


def test_fresh_camera_without_detected_markers_can_finish_as_missing_geometry():
    with scripted_recording() as (rig, clock):
        read = camera_reader(clock)
        def camera():
            sample = read()
            sample['vision']['age_since_host_read_s'] = .01
            if clock.now_ns > 2_000_000_000:
                sample['vision'].update(detected=False, image_angle_rad=None, pivot_px=None, bob_px=None, length_px=None)
            return sample
        result = probe.run_passive(rig, seconds=1., camera_read=camera,
                                   finish_requested=lambda: clock.now_ns >= 2_300_000_000)
    assert result['finish_reason'] == 'operator_done'
    assert_no_motion(rig)


class StallingCameraHandler(CameraHandler):
    def do_GET(self):
        if self.path == '/api/clock':
            return super().do_GET()
        self.send_response(200)
        self.end_headers()
        stamp = time.monotonic()
        row = dict(schema='cartpole-sensing-stream-v1', stream_seq=1, host_t=stamp,
                   vision=dict(seq=1, t=stamp, stale=False, age_since_host_read_s=0., worker_error=None))
        self.wfile.write((json.dumps(row) + '\n').encode())
        self.wfile.flush()
        self.server.release_stream.wait(3.)


def test_camera_close_during_actual_stalled_http_read_preserves_timeout(tmp_path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), StallingCameraHandler)
    server.release_stream = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    recorder = probe.CameraRecorder(f'http://127.0.0.1:{server.server_port}/stream', tmp_path, 10.)
    try:
        recorder.start()
        time.sleep(.05)  # The ready child has entered the next blocking readline.
        report = recorder.close()
        assert 'timed out' in report.get('failure', '')
        assert report['frames'] == 1
    finally:
        if recorder.process.is_alive():
            recorder.close()
        server.release_stream.set()
        server.shutdown()
        server.server_close()
        thread.join(2.)


@pytest.mark.parametrize('latch_stage', ('finish_callback', 'camera_finish_read', 'rig_close'))
def test_passive_finish_and_report_never_hide_latched_rig_failure(tmp_path, latch_stage):
    with scripted_recording() as (rig, clock):
        error = RuntimeError('injected logger failure')
        original_close = rig.close
        class Camera:
            def __init__(self, *_):
                pass
            def start(self):
                pass
            def check(self):
                pass
            def latest(self):
                if latch_stage == 'camera_finish_read' and clock.now_ns >= 2_300_000_000:
                    rig._latch(error)
                return camera_reader(clock)()
            def close(self):
                return {'frames': 100}
        def finish():
            if clock.now_ns < 2_300_000_000:
                return False
            if latch_stage == 'finish_callback':
                rig._latch(error)
            return True
        def close():
            if latch_stage == 'rig_close':
                rig._latch(error)
            original_close()
        rig.close = close
        with pytest.raises(RuntimeError, match='injected logger failure'):
            probe.collect('passive', output=tmp_path/'run', port='offline', seconds=30.,
                          rig_factory=lambda *args, **kwargs: rig, camera_factory=Camera,
                          finish_requested=finish)
    report = json.loads((tmp_path/'run'/'report.json').read_text())
    assert report['completed'] is False
    assert 'injected logger failure' in report['failure']
    assert next(row for row in rig.records if row['type'] == 'termination')['error'] == 'injected logger failure'
    assert_no_motion(rig)
