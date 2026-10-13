#!/usr/bin/env python3
"""Compile and upload an Arduino sketch (ESP32 by default). No Python packages needed."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent


def run(command):
    subprocess.run(command, check=True)


def sketch_path(value):
    candidate = Path(value).expanduser()
    if not candidate.exists():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    if candidate.is_file() and candidate.suffix == ".ino":
        candidate = candidate.parent
    if not candidate.is_dir() or not (candidate / (candidate.name + ".ino")).is_file():
        raise ValueError(f"Sketch not found: {value}. Use a sketch folder or its .ino file.")
    return candidate


def find_port(cli):
    result = subprocess.run([cli, "board", "list", "--format", "json"],
                            check=True, capture_output=True, text=True)
    ports = []
    for item in json.loads(result.stdout).get("detected_ports", []):
        port = item.get("port", {})
        address = port.get("address", "")
        properties = port.get("properties", {})
        if port.get("protocol") == "serial" and (
            properties.get("vid") or "usbserial" in address.lower()
            or "usbmodem" in address.lower() or address.startswith(("/dev/ttyUSB", "/dev/ttyACM"))
        ):
            ports.append(address)
    ports = sorted(set(ports))
    if len(ports) != 1:
        found = ", ".join(ports) if ports else "none"
        raise ValueError(f"Expected one USB serial port; found {found}. Specify --port PORT.")
    return ports[0]


def check_port_available(port):
    lsof = shutil.which("lsof")
    if not lsof or not port.startswith("/dev/"):
        return
    # On macOS a console may hold the /dev/tty.* alias of a /dev/cu.* port.
    paths = [port]
    if port.startswith("/dev/cu."):
        alias = port.replace("/dev/cu.", "/dev/tty.", 1)
        if Path(alias).exists():
            paths.append(alias)
    result = subprocess.run([lsof, "-t", *paths], capture_output=True, text=True)
    if result.stdout.strip():
        raise ValueError(f"Port {port} is busy. Close the serial console/plotter before flashing "
                         f"(process IDs: {', '.join(result.stdout.split())}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sketch", nargs="?", default="swingup",
                        help="sketch name, folder, or .ino path (default: swingup)")
    parser.add_argument("--port", "-p", help="serial port; otherwise detect the single USB device")
    parser.add_argument("--fqbn", default="esp32:esp32:esp32", help="Arduino board identifier")
    parser.add_argument("--compile-only", action="store_true", help="build without accessing hardware")
    parser.add_argument("--libraries", action="append", default=[], metavar="DIR",
                        help="additional Arduino library directory (repeatable)")
    parser.add_argument("--cli", default="arduino-cli", help="Arduino CLI executable or path")
    args = parser.parse_args()
    try:
        sketch = sketch_path(args.sketch)
        cli = shutil.which(args.cli)
        if not cli:
            raise ValueError("arduino-cli not found. Install it and the board core; "
                             "see README.md, or pass --cli /path/to/arduino-cli.")
        port = None
        if not args.compile_only:
            port = args.port or find_port(cli)
            check_port_available(port)
        with tempfile.TemporaryDirectory(prefix="cartpole-flash-") as temporary:
            work = Path(temporary)
            build = work / "build"
            command = [cli, "compile", "--fqbn", args.fqbn, "--build-path", str(build)]
            bundled = ROOT / "third_party" / "FastAccelStepper-1.2.8.zip"
            if bundled.is_file():
                libraries = work / "libraries"
                with zipfile.ZipFile(bundled) as archive:
                    archive.extractall(libraries)
                command += ["--libraries", str(libraries)]
            for directory in args.libraries:
                command += ["--libraries", str(Path(directory).expanduser().resolve())]
            print(f"Compiling {sketch.name} for {args.fqbn}…", flush=True)
            run(command + [str(sketch)])
            if args.compile_only:
                print("Compile succeeded. Nothing uploaded.")
                return 0
            check_port_available(port)
            print(f"Uploading {sketch.name} to {port}…", flush=True)
            run([cli, "upload", "--fqbn", args.fqbn, "--port", port,
                 "--input-dir", str(build), str(sketch)])
        print("Flash complete.")
        return 0
    except subprocess.CalledProcessError as error:
        print(f"Arduino CLI failed (exit {error.returncode}). Flash did not complete.", file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled. Flash did not complete.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
