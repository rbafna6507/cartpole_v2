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
