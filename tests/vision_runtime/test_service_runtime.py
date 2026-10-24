import json
from pathlib import Path
import pytest
from cartpole_vision import live
from cartpole_vision import runtime


def test_camera_watchdog_rejects_stall_but_allows_startup():
    assert runtime.camera_failure({"error": None, "latest_age_s": None}, .5, 2) is None
    assert "no frame" in runtime.camera_failure({"error": None, "latest_age_s": None}, 3, 2)
    assert "stalled" in runtime.camera_failure({"error": None, "latest_age_s": 3}, 3, 2)
    assert runtime.camera_failure({"error": None, "latest_age_s": .01}, 3, 2) is None
    assert "unplugged" in runtime.camera_failure({"error": "unplugged", "latest_age_s": .01}, 3, 2)


def test_jsonl_rotation_bounds_storage_and_preserves_complete_records(tmp_path):
    log = runtime.JsonlLog(tmp_path / "states.jsonl", max_bytes=100, backups=2)
    for i in range(100): log.write(json.dumps({"sequence": i, "payload": "x" * 30}) + "\n")
    log.close()
    paths = list(tmp_path.iterdir())
    assert len(paths) == 3
    assert sum(p.stat().st_size for p in paths) <= 300
    assert json.loads((tmp_path / "states.jsonl").read_text().splitlines()[-1])["sequence"] == 99
    for path in paths:
        for line in path.read_text().splitlines(): assert isinstance(json.loads(line), dict)


def test_retention_only_deletes_marked_viewer_sessions(tmp_path):
    protected = tmp_path / "unrelated"
    protected.mkdir()
    for i in range(5):
        d = tmp_path / str(i); d.mkdir(); (d / ".cartpole-vision-session").touch()
    runtime.prune_sessions(tmp_path, keep=2)
    assert protected.is_dir()
    assert len([p for p in tmp_path.iterdir() if (p / ".cartpole-vision-session").exists()]) == 2


def test_runtime_options_validate_before_camera():
    a = live.arguments([])
    assert a.fps == 30
    assert not a.record
    assert a.camera_timeout == 2
    assert a.sdk_port == 3097
    for flags in (["--camera-timeout", "0"], ["--keep-sessions", "0"], ["--port", "0"], ["--sdk-port", "65536"]):
        with pytest.raises(SystemExit): live.arguments(flags)


def test_jsonl_disk_full_is_reported_and_recovers(tmp_path, monkeypatch):
    import errno
    original = Path.open
    def full(*args, **kwargs):
        raise OSError(errno.ENOSPC, 'No space left on device')
    monkeypatch.setattr(Path, 'open', full)
    log = runtime.JsonlLog(tmp_path / 'states.jsonl', retry_seconds=0)
    assert log.write('{"seq":1}\n') is False
    assert 'No space' in log.report()['error']
    monkeypatch.setattr(Path, 'open', original)
    assert log.write('{"seq":2}\n') is True
    assert log.report()['error'] is None
    assert log.report()['dropped_records'] == 1
    assert log.report()['written_records'] == 1
    log.close()
    assert json.loads((tmp_path / 'states.jsonl').read_text())['seq'] == 2


def test_jsonl_low_space_stops_recording_without_raising(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(runtime.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    log = runtime.JsonlLog(tmp_path / 'states.jsonl')
    assert log.write('{}\n') is False
    assert 'reserve' in log.report()['error']
    log.flush()
    log.close()


def test_raw_recording_failure_does_not_raise_into_tracking(tmp_path, monkeypatch):
    from cartpole_vision.capture import BufferedRecorder, RawRecorder
    def fail(*args, **kwargs):
        raise OSError(28, 'disk full')
    monkeypatch.setattr(RawRecorder, '__init__', fail)
    recorder = BufferedRecorder(tmp_path, 80)
    recorder.write(None, 1, 1.0)
    assert recorder.error
    assert recorder.dropped == 1
    recorder.close()


def test_jsonl_partial_write_is_removed_before_recovery(tmp_path):
    log = runtime.JsonlLog(tmp_path / 'states.jsonl', retry_seconds=0)
    log.write('{"seq":1}\n')
    original = log.file
    class PartialWriter:
        def write(self, data):
            original.write(data[:3])
            raise OSError(28, 'disk full')
        def close(self): original.close()
    log.file = PartialWriter()
    assert log.write('{"seq":2}\n') is False
    assert log.write('{"seq":3}\n') is True
    log.close()
    assert [json.loads(row)['seq'] for row in (tmp_path / 'states.jsonl').read_text().splitlines()] == [1, 3]


def test_jsonl_flush_and_close_errors_do_not_escape(tmp_path):
    log = runtime.JsonlLog(tmp_path / 'states.jsonl')
    class FailedFile:
        def flush(self): raise OSError(28, 'disk full')
        def close(self): raise OSError(28, 'disk full')
    log.file = FailedFile()
    log.flush()
    assert log.report()['error']
    log.file = FailedFile()
    log.close()


def test_raw_recording_stops_at_disk_budget(tmp_path):
    import numpy as np
    from cartpole_vision.capture import RawRecorder
    recorder = RawRecorder(tmp_path, 80, max_bytes=1)
    try:
        with pytest.raises(OSError, match='limit'):
            recorder.write(np.zeros((48, 64, 3), dtype=np.uint8), 1, 1.0)
    finally:
        recorder.close()


def test_live_keeps_tracking_and_video_when_disk_is_full(tmp_path, monkeypatch):
    import time
    import numpy as np
    from types import SimpleNamespace
    from cartpole_vision.app import Engine
    from cartpole_vision.encoder_feed import Comparison
    engines = []
    class FakeCamera:
        def __init__(self, *args): self.seq = 0
        def get(self):
            self.seq += 1
            return self.seq, time.monotonic(), np.zeros((48, 64, 3), dtype=np.uint8)
        def report(self): return dict(error=None, latest_age_s=0)
        def close(self): pass
    class FakeVideo:
        error = None
        def __init__(self, *args): pass
        def report(self): return dict(running=True)
        def close(self): pass
    class FakeServer:
        def handle_request(self): time.sleep(.005)
        def server_close(self): pass
    def engine(*args):
        result = Engine(*args)
        engines.append(result)
        return result
    def full(*args, **kwargs): raise OSError(28, 'disk full')
    monkeypatch.setattr(Path, 'write_text', full)
    monkeypatch.setattr(runtime.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(live, 'Camera', FakeCamera)
    monkeypatch.setattr(live, 'Engine', engine)
    monkeypatch.setattr(live, 'ComparisonProcess', lambda *args: Comparison())
    monkeypatch.setattr(live, 'PreviewWorker', lambda *args: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(live, 'VideoStream', FakeVideo)
    monkeypatch.setattr(live, 'make_server', lambda *args, **kwargs: FakeServer())
    live.main(['--out', str(tmp_path), '--duration', '.1', '--encoder-port', '0', '--sdk-port', '0'])
    report = engines[0].snapshot()
    assert report['processed_frames'] > 2
    assert report['worker_error'] is None
    assert report['video']['running']
    assert report['telemetry_recording']['dropped_records'] > 2
    assert report['telemetry_recording']['error']
    assert 'disk full' in report['recording_setup_error']
