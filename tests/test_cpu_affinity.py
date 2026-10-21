"""Reversible CPU partitioning without camera, serial, or systemd access."""
from contextlib import nullcontext
import io
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest


def affinity_module():
    from cartpole_sdk.rig import cpu_affinity
    return cpu_affinity


class FakeProc:
    def __init__(self, module):
        self.module = module
        self.items = {}
        self.masks = {}
        self.events = []
        self.fail = None
        self.add_process(100, 10, 1, {100: {0, 1, 2, 3, 4, 5}, 101: {2, 3}})
        self.add_process(200, 20, 100, {200: {0, 1, 2, 3, 4, 5}, 201: {4, 5}})

    def add_process(self, pid, start, parent, threads):
        process = self.module.ProcessIdentity(pid, start, parent)
        self.items[pid] = (process, {})
        for tid, cpus in threads.items():
            self.add_thread(pid, tid, start + tid, cpus)

    def add_thread(self, pid, tid, start, cpus):
        process, threads = self.items[pid]
        identity = self.module.ThreadIdentity(pid, process.start, tid, start)
        threads[tid] = identity
        self.masks[tid] = set(cpus)

    def processes(self):
        return {pid: item[0] for pid, item in self.items.items()}

    def threads(self, process):
        return list(self.items[process.pid][1].values())

    def alive(self, thread):
        item = self.items.get(thread.pid)
        return bool(item and item[0].start == thread.process_start and item[1].get(thread.tid) == thread)

    def get_affinity(self, thread):
        if not self.alive(thread):
            raise ProcessLookupError(thread.tid)
        return set(self.masks[thread.tid])

    def set_affinity(self, thread, cpus):
        assert self.alive(thread), 'never operate on a reused process or thread identity'
        self.events.append((thread.tid, set(cpus)))
        if self.fail is not None:
            self.fail(thread, cpus)
        self.masks[thread.tid] = set(cpus)


@pytest.mark.parametrize('value', ['', '-1', '2-1', '1,,2', '1-a', '1.5', '0-999999999'])
def test_rejects_invalid_or_unavailable_cpu_lists(value):
    m = affinity_module()
    with pytest.raises(m.AffinityError):
        m.parse_cpus(value, available={0, 1, 2, 3, 4, 5})


def test_cpu_lists_are_nonempty_available_and_disjoint():
    m = affinity_module()
    assert m.parse_cpus('0-2,4', available=set(range(6))) == {0, 1, 2, 4}
    with pytest.raises(m.AffinityError, match='disjoint'):
        m.validate_partition({0, 1}, {1, 2}, set(range(6)))
    with pytest.raises(m.AffinityError, match='available'):
        m.validate_partition({0, 1}, {7}, set(range(6)))


@pytest.mark.parametrize('failure', [None, ValueError('command failed'), KeyboardInterrupt()])
def test_restores_every_original_thread_mask_on_all_exits(failure):
    m = affinity_module()
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    expected = nullcontext() if failure is None else pytest.raises(type(failure))
    with expected:
        with m.CameraAffinity(100, {0, 1}, proc=proc):
            assert all(cpus == {0, 1} for cpus in proc.masks.values())
            if failure is not None:
                raise failure
    assert proc.masks == original
    assert all(tid != 0 and tid != os.getpid() for tid, _ in proc.events)


def test_restores_new_threads_and_descendants_using_original_process_mask():
    m = affinity_module()
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    with m.CameraAffinity(100, {0, 1}, proc=proc) as camera:
        proc.add_thread(100, 102, 112, {0, 1})
        proc.add_process(300, 30, 200, {300: {0, 1}})
        camera.refresh()
        # A discovered descendant remains ours to restore after reparenting.
        process, threads = proc.items[300]
        proc.items[300] = (m.ProcessIdentity(300, 30, 1), threads)
        proc.add_thread(300, 301, 331, {0, 1})
    assert proc.masks == original | {102: set(range(6)), 300: set(range(6)), 301: set(range(6))}


def test_partial_apply_failure_rolls_back_before_command_can_launch():
    m = affinity_module()
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    def fail(thread, cpus):
        if thread.tid == 201 and cpus == {0, 1}:
            raise PermissionError('refused camera affinity')
    proc.fail = fail
    with pytest.raises((m.AffinityError, PermissionError), match='refused'):
        with m.CameraAffinity(100, {0, 1}, proc=proc):
            pytest.fail('must not launch after partial affinity failure')
    assert proc.masks == original


def test_restore_failure_is_reported_and_other_threads_are_still_restored():
    m = affinity_module()
    proc = FakeProc(m)
    def fail(thread, cpus):
        if thread.tid == 101 and cpus == {2, 3}:
            raise PermissionError('restore denied')
    with pytest.raises(m.AffinityError, match='restor.*101'):
        with m.CameraAffinity(100, {0, 1}, proc=proc):
            proc.fail = fail
    assert proc.masks[100] == set(range(6)) and proc.masks[201] == {4, 5}
    assert proc.masks[101] == {0, 1}


def test_pid_reuse_never_applies_old_camera_mask_to_replacement():
    m = affinity_module()
    proc = FakeProc(m)
    with m.CameraAffinity(100, {0, 1}, proc=proc):
        proc.add_process(100, 999, 1, {100: {5}, 101: {5}})
        process, threads = proc.items[200]
        proc.items[200] = (m.ProcessIdentity(200, 20, 1), threads)
        proc.events.clear()
    assert not any(tid in (100, 101) for tid, _ in proc.events)
    assert proc.masks[100] == {5} and proc.masks[101] == {5}
    assert proc.masks[200] == set(range(6))


def test_reused_tid_in_live_camera_gets_process_default_not_old_thread_mask():
    m = affinity_module()
    proc = FakeProc(m)
    with m.CameraAffinity(100, {0, 1}, proc=proc):
        proc.add_thread(100, 101, 999, {0, 1})
    assert proc.masks[101] == set(range(6))


def test_systemd_main_pid_lookup_is_read_only_and_absence_is_an_error(monkeypatch):
    m = affinity_module()
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, '123\n', '')
    monkeypatch.setattr(m.subprocess, 'run', run)
    assert m.service_main_pid('cartpole-vision.service') == 123
    assert calls == [['systemctl', '--user', 'show', '--property=MainPID', '--value', 'cartpole-vision.service']]
    monkeypatch.setattr(m.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, '0\n', ''))
    with pytest.raises(m.AffinityError, match='running'):
        m.service_main_pid('cartpole-vision.service')


class FakeChild:
    pid = 50000
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.returncode = None
        self.waits = []
    def wait(self, timeout=None):
        self.waits.append(timeout)
        value = next(self.outcomes)
        if isinstance(value, BaseException):
            raise value
        self.returncode = value
        return value
    def poll(self):
        return self.returncode


def test_interrupt_keeps_interactive_child_and_camera_partition_until_voluntary_exit(monkeypatch):
    m = affinity_module()
    child = FakeChild([KeyboardInterrupt(), subprocess.TimeoutExpired('child', 10), KeyboardInterrupt(), 0])
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    def no_early_restore(thread, cpus):
        if cpus != {0, 1}:
            assert child.returncode is not None, 'camera must stay restricted while console remains alive'
    proc.fail = no_early_restore
    launches, sent = [], []
    monkeypatch.setattr(m.subprocess, 'Popen', lambda args, **kwargs: launches.append((args, kwargs)) or child)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: sent.append((pid, sig)))
    with m.CameraAffinity(100, {0, 1}, proc=proc) as camera:
        assert m.run_control(['example', 'argument with spaces'], {4, 5}, camera=camera, output=io.StringIO()) == 0
        assert all(mask == {0, 1} for mask in proc.masks.values())
    assert launches[0][0][-2:] == ['example', 'argument with spaces']
    assert launches[0][1]['start_new_session'] is True
    assert sent == [(50000, signal.SIGINT), (50000, signal.SIGINT)]
    assert proc.masks == original
    assert all(timeout <= 1 for timeout in child.waits)


@pytest.mark.parametrize('failure', [RuntimeError('monitor failure'), 'term', 'hup'])
def test_fatal_parent_error_or_term_allows_stop_grace_before_escalating(monkeypatch, failure):
    m = affinity_module()
    if failure == 'term':
        failure = m._Terminated()
    elif failure == 'hup':
        failure = m._Terminated(signal.SIGHUP)
    child = FakeChild([failure, subprocess.TimeoutExpired('child', 10), 0])
    sent = []
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: sent.append((pid, sig)))
    with pytest.raises(type(failure)):
        m.run_control(['example'], {4, 5}, output=io.StringIO())
    assert sent == [(50000, signal.SIGINT), (50000, signal.SIGTERM)]
    assert child.waits[1] >= 5


class BrokenOutput:
    def __init__(self, error):
        self.error = error
    def write(self, value):
        raise self.error
    def flush(self):
        raise self.error


@pytest.mark.parametrize('error', [OSError(5, 'hung up PTY'), BrokenPipeError('closed SSH pipe'), ValueError('closed stream')])
def test_hangup_cleanup_signals_and_waits_even_when_diagnostics_are_unwritable(monkeypatch, error):
    m = affinity_module()
    child = FakeChild([m._Terminated(signal.SIGHUP), 0])
    sent = []
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: sent.append((pid, sig)))
    with pytest.raises(m._Terminated):
        m.run_control(['example'], {4, 5}, output=BrokenOutput(error))
    assert sent == [(50000, signal.SIGINT)]
    assert child.returncode == 0 and child.waits[1] >= 5


def test_interrupt_forwarding_does_not_depend_on_diagnostic_output(monkeypatch):
    m = affinity_module()
    child = FakeChild([KeyboardInterrupt(), 0])
    sent = []
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: sent.append((pid, sig)))
    assert m.run_control(['example'], {4, 5}, output=BrokenOutput(OSError(5, 'hung up PTY'))) == 0
    assert sent == [(50000, signal.SIGINT)]


def test_proc_identity_parser_accepts_spaces_and_parentheses(tmp_path):
    m = affinity_module()
    directory = tmp_path / '123'
    directory.mkdir()
    (directory / 'stat').write_text('123 (odd ) worker) S 7 '+'0 '*17+'456 0\n')
    proc = m.ProcFS(tmp_path)
    process = proc.processes()[123]
    assert (process.pid, process.start, process.parent) == (123, 456, 7)


def pretend_linux(monkeypatch, module):
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    monkeypatch.setattr(module.os, 'sched_getaffinity', lambda pid: set(range(6)), raising=False)


def test_failed_command_spawn_restores_camera_and_reports_failure(monkeypatch, capsys):
    m = affinity_module()
    pretend_linux(monkeypatch, m)
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    camera = m.CameraAffinity(100, {0, 1}, proc=proc)
    monkeypatch.setattr(m, 'CameraAffinity', lambda *args: camera)
    monkeypatch.setattr(m, 'service_main_pid', lambda service: 100)
    def fail(*args, **kwargs):
        raise FileNotFoundError('missing command executable')
    monkeypatch.setattr(m.subprocess, 'Popen', fail)
    assert m.main(['--camera-service', 'camera.service', '--camera-cpus', '0-1', '--control-cpus', '4-5', '--', 'missing']) == 1
    assert proc.masks == original
    assert 'missing command executable' in capsys.readouterr().err


def test_cli_restore_failure_never_prints_success(monkeypatch, capsys):
    m = affinity_module()
    pretend_linux(monkeypatch, m)
    proc = FakeProc(m)
    camera = m.CameraAffinity(100, {0, 1}, proc=proc)
    monkeypatch.setattr(m, 'CameraAffinity', lambda *args: camera)
    monkeypatch.setattr(m, 'service_main_pid', lambda service: 100)
    def control(*args, **kwargs):
        def deny(thread, cpus):
            raise PermissionError('restore unavailable')
        proc.fail = deny
        return 0
    monkeypatch.setattr(m, 'run_control', control)
    assert m.main(['--camera-service', 'camera.service', '--camera-cpus', '0-1', '--control-cpus', '4-5', '--', 'control']) == 1
    output = capsys.readouterr().err
    assert 'restoration failed' in output and 'camera affinity restored' not in output


def test_no_camera_does_not_look_up_or_modify_camera_and_propagates_exit(monkeypatch):
    m = affinity_module()
    pretend_linux(monkeypatch, m)
    def forbidden(*args, **kwargs):
        pytest.fail('explicit no-camera mode must not discover a camera')
    monkeypatch.setattr(m, 'service_main_pid', forbidden)
    monkeypatch.setattr(m, 'run_control', lambda command, cpus, **kwargs: 17 if command == ['command'] and cpus == {4, 5} and kwargs['camera'] is None else 99)
    assert m.main(['--no-camera', '--control-cpus', '4-5', '--', 'command']) == 17


def test_invalid_partition_is_rejected_before_camera_lookup_or_command(monkeypatch):
    m = affinity_module()
    pretend_linux(monkeypatch, m)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid partition must have no process side effects')
    monkeypatch.setattr(m, 'service_main_pid', forbidden)
    monkeypatch.setattr(m, 'run_control', forbidden)
    assert m.main(['--camera-service', 'camera.service', '--camera-cpus', '0-4', '--control-cpus', '4-5', '--', 'control']) == 1


@pytest.mark.parametrize('diagnostic_error', [None, OSError(5, 'hung up PTY'), BrokenPipeError('closed SSH pipe')])
def test_ssh_hangup_stops_child_restores_camera_and_restores_signal_handler(monkeypatch, diagnostic_error):
    m = affinity_module()
    pretend_linux(monkeypatch, m)
    proc = FakeProc(m)
    original = {tid: set(cpus) for tid, cpus in proc.masks.items()}
    camera = m.CameraAffinity(100, {0, 1}, proc=proc)
    before_hup = signal.getsignal(signal.SIGHUP)
    class HangupChild(FakeChild):
        def wait(self, timeout=None):
            if not self.waits:
                self.waits.append(timeout)
                handler = signal.getsignal(signal.SIGHUP)
                assert callable(handler), 'launcher must catch SSH hangup'
                handler(signal.SIGHUP, None)
            return super().wait(timeout)
    child = HangupChild([0])
    sent = []
    monkeypatch.setattr(m, 'CameraAffinity', lambda *args: camera)
    monkeypatch.setattr(m, 'service_main_pid', lambda service: 100)
    def spawn(*args, **kwargs):
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        assert signal.SIGHUP in mask, 'hangup cannot lose a newly created child handle'
        return child
    monkeypatch.setattr(m.subprocess, 'Popen', spawn)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: sent.append((pid, sig)))
    with monkeypatch.context() as output_patch:
        if diagnostic_error is not None:
            output_patch.setattr(m.sys, 'stderr', BrokenOutput(diagnostic_error))
        code = m.main(['--camera-service', 'camera.service', '--camera-cpus', '0-1', '--control-cpus', '4-5', '--', 'control'])
    assert code == 129
    assert sent == [(50000, signal.SIGINT)]
    assert proc.masks == original
    assert signal.getsignal(signal.SIGHUP) is before_hup


def test_hangup_is_deferred_during_restoration():
    m = affinity_module()
    before = signal.getsignal(signal.SIGHUP)
    with m._ignore_cleanup_signals():
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    assert signal.getsignal(signal.SIGHUP) is before


def test_launcher_help_works_without_installing_project_or_optional_dependencies():
    script = Path(__file__).resolve().parents[1] / 'scripts/jetson-control'
    result = subprocess.run([sys.executable, '-I', str(script), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '--control-cpus' in result.stdout and '--no-camera' in result.stdout


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='actual Linux scheduler API')
def test_short_child_is_pinned_without_changing_parent_affinity(tmp_path):
    m = affinity_module()
    original = os.sched_getaffinity(0)
    cpus = {min(original)}
    target = tmp_path / 'mask.txt'
    command = [sys.executable, '-c', 'import os,pathlib,sys;pathlib.Path(sys.argv[1]).write_text(str(sorted(os.sched_getaffinity(0))))', str(target)]
    assert m.run_control(command, cpus, output=io.StringIO()) == 0
    assert target.read_text() == str(sorted(cpus))
    assert os.sched_getaffinity(0) == original
