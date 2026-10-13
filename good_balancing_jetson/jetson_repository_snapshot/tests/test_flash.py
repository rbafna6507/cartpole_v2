"""Offline checks: never access a serial device."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("flash", Path(__file__).resolve().parents[1] / "flash.py")
flash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)


class FlashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flash test ")
        self.addCleanup(self.temp.cleanup)
        self.sketch = Path(self.temp.name) / "example"
        self.sketch.mkdir()
        (self.sketch / "example.ino").write_text("void setup() {}\nvoid loop() {}\n")

    def invoke(self, extra=(), fail_compile=False):
        calls = []

        def command(argv):
            calls.append(argv)
            if fail_compile and argv[1] == "compile":
                raise subprocess.CalledProcessError(1, argv)

        with patch.object(sys, "argv", ["flash.py", str(self.sketch), *extra]), \
             patch.object(flash.shutil, "which", return_value="/fake/arduino-cli"), \
             patch.object(flash, "check_port_available"), \
             patch.object(flash, "run", side_effect=command):
            status = flash.main()
        return status, calls

    def test_upload_uses_fresh_compile_directory_and_handles_spaces(self):
        status, calls = self.invoke(["--port", "/dev/example", "--fqbn", "vendor:core:board"])
        self.assertEqual(status, 0)
        self.assertEqual([c[1] for c in calls], ["compile", "upload"])
        self.assertEqual(calls[0][calls[0].index("--build-path") + 1],
                         calls[1][calls[1].index("--input-dir") + 1])
        self.assertEqual(calls[1][-1], str(self.sketch.resolve()))
        self.assertIn("vendor:core:board", calls[0])
        self.assertIn("vendor:core:board", calls[1])

    def test_compile_failure_never_uploads(self):
        status, calls = self.invoke(["--port", "/dev/example"], fail_compile=True)
        self.assertEqual(status, 1)
        self.assertEqual([c[1] for c in calls], ["compile"])

    def test_compile_only_never_discovers_device(self):
        with patch.object(flash, "find_port", side_effect=AssertionError("hardware accessed")):
            status, calls = self.invoke(["--compile-only"])
        self.assertEqual(status, 0)
        self.assertEqual([c[1] for c in calls], ["compile"])

    def test_repo_name_and_ino_paths(self):
        with patch.object(flash, "ROOT", Path(self.temp.name)):
            self.assertEqual(flash.sketch_path("example"), self.sketch.resolve())
            self.assertEqual(flash.sketch_path(self.sketch / "example.ino"), self.sketch.resolve())
        with self.assertRaises(ValueError):
            flash.sketch_path(self.sketch / "missing.ino")

    def test_port_discovery_requires_single_usb(self):
        import json
        def ports(addresses):
            return json.dumps({"detected_ports": [{"port": {"address": a, "protocol": "serial"}}
                                                     for a in addresses]})
        for addresses, expected in [(["/dev/cu.wlan-debug", "/dev/cu.Bluetooth-Incoming-Port"], None),
                                    (["/dev/cu.usbserial-0001"], "/dev/cu.usbserial-0001"),
                                    (["/dev/ttyUSB0", "/dev/ttyUSB1"], None)]:
            with patch.object(flash.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, ports(addresses))):
                if expected:
                    self.assertEqual(flash.find_port("cli"), expected)
                else:
                    with self.assertRaises(ValueError):
                        flash.find_port("cli")

    def test_busy_port_rejected(self):
        with patch.object(flash.shutil, "which", return_value="lsof"), \
             patch.object(flash.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "123\n")):
            with self.assertRaisesRegex(ValueError, "busy"):
                flash.check_port_available("/dev/example")


if __name__ == "__main__":
    unittest.main()
