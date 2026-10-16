"""Bounded on-disk diagnostics and camera liveness for unattended viewing."""
from pathlib import Path
import shutil
import threading


class JsonlLog:
    """Rotate before complete records; default footprint is at most 32 MiB."""
    def __init__(self, path, max_bytes=8 * 1024 * 1024, backups=3):
        self.path = Path(path)
        self.max_bytes, self.backups = max_bytes, backups
        self.lock = threading.Lock()
        self.file = self.path.open("a", buffering=65536)
        self.size = self.path.stat().st_size

    def write(self, text):
        size = len(text.encode("utf-8"))
        if size > self.max_bytes:
            raise ValueError("Telemetry record exceeds log limit")
        with self.lock:
            if self.size + size > self.max_bytes:
                self.file.close()
                for i in range(self.backups, 0, -1):
                    src = self.path if i == 1 else Path(f"{self.path}.{i - 1}")
                    if src.exists(): src.replace(Path(f"{self.path}.{i}"))
                self.file = self.path.open("w", buffering=65536)
                self.size = 0
            self.file.write(text)
            self.size += size

    def flush(self):
        with self.lock: self.file.flush()

    def close(self):
        with self.lock: self.file.close()

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()


def prune_sessions(directory, keep=4):
    """Only directories marked by this runtime are eligible for deletion."""
    sessions = [p for p in Path(directory).iterdir()
                if p.is_dir() and not p.is_symlink() and (p / ".cartpole-vision-session").is_file()]
    for path in sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        shutil.rmtree(path)


def camera_failure(report, elapsed, timeout):
    if report.get("error"): return f"Camera failed: {report['error']}"
    age = report.get("latest_age_s")
    if age is None and elapsed > timeout: return "Camera produced no frame before timeout"
    if age is not None and age > timeout: return f"Camera stalled for {age:.2f} seconds"
    return None
