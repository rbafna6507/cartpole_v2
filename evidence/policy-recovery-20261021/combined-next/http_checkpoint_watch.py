#!/usr/bin/env python3
"""Bounded HTTP-only backups for the frozen filtered BAL joint campaign.

Only the pinned CLI's download command is invoked. No kernel execution,
allocation, training lifecycle operation, or credential output is available.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REMOTE_ROOT = '/content/cartpole-training/'
PROTOCOL_PATH = 'evidence/policy-recovery-20261021/combined-next/protocol.json'
EXPECTED_PROTOCOL = '9c1d048ceb19b8e1b3f59a05c3540cf80096401be8660b556f1c981c0b593e68'
SESSION = 'filtered-bal-joint-long-20261021'
RUNS = {f'runs/combined-long/{arm}-seed{seed}': (arm, seed)
        for seed in (11, 23, 47) for arm in ('ppo', 'retained')}
SHA = re.compile(r'[0-9a-f]{64}')


class DownloadError(Exception):
    """Transport failure with intentionally sanitized diagnostics."""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def download_cli(executable, state_file, session, remote, destination, timeout):
    if not math.isfinite(timeout) or not 0 < timeout <= 45:
        raise ValueError('download deadline must be positive and at most 45 seconds')
    command = [str(executable), '--auth', 'oauth2', '--config', str(state_file),
               'download', '-s', session, remote, str(destination)]
    try:
        subprocess.run(command, check=True, timeout=timeout, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise DownloadError('download deadline exceeded') from None
    except (subprocess.CalledProcessError, OSError):
        raise DownloadError('download subprocess failed') from None
    if not destination.is_file():
        raise DownloadError('download did not create a file')


def validate_zip(path, expected):
    if path.is_symlink() or digest(path) != expected:
        raise ValueError('checkpoint SHA mismatch or symlink')
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('checkpoint ZIP CRC failure')


def poll(download, output, expected_protocol, *, deadline=None, clock=time.monotonic):
    """Back up one atomic status snapshot's current and completed trial reports."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if not SHA.fullmatch(expected_protocol):
        raise ValueError('invalid protocol SHA')
    def fetch(remote, local):
        remaining = 45 if deadline is None else min(45, deadline - clock())
        if remaining <= 0:
            raise TimeoutError('watch deadline reached')
        download(REMOTE_ROOT + remote, local, remaining)
    def retain_metadata(path, category):
        dest = output / 'metadata' / category / (digest(path) + '.json')
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.read_bytes() != path.read_bytes():
                raise ValueError('immutable metadata conflict')
        else:
            with dest.open('xb') as stream:
                stream.write(path.read_bytes())
        return str(dest.relative_to(output))
    with tempfile.TemporaryDirectory(prefix='.download-', dir=output) as staging:
        staging = Path(staging)
        remote_protocol = staging / 'protocol.json'
        fetch(PROTOCOL_PATH, remote_protocol)
        if digest(remote_protocol) != expected_protocol:
            raise ValueError('remote protocol mismatch')
        status_path = staging / 'job-status.json'
        fetch('job-status.json', status_path)
        state = json.loads(status_path.read_text())
        if state.get('status') not in ('training', 'completed', 'failed'):
            raise ValueError('unexpected job status')
        current = state.get('run')
        if current not in RUNS:
            raise ValueError('unlisted current run')
        completed = {}
        for row in state.get('completed_trials', []):
            run = row.get('run')
            if run not in RUNS or run in completed or (row.get('arm'), row.get('seed')) != RUNS[run]:
                raise ValueError('invalid completed trial identity')
            if not SHA.fullmatch(row.get('report_sha256', '')):
                raise ValueError('invalid completed report SHA')
            completed[run] = row['report_sha256']
        if state['status'] == 'completed' and set(completed) != set(RUNS):
            raise ValueError('incomplete completed-job trial list')
        runs = list(completed) + ([] if current in completed else [current])
        result = dict(status='backup_complete', remote_status=state['status'],
                      protocol_sha256=expected_protocol, observed_at_unix=time.time(),
                      job_status_sha256=digest(status_path), reports=[], checkpoints=[])
        for index, run in enumerate(runs):
            report_path = staging / f'report-{index}.json'
            fetch(run + '/report.json', report_path)
            report = json.loads(report_path.read_text())
            if report.get('protocol_sha256') != expected_protocol:
                raise ValueError('report protocol mismatch')
            if (report.get('arm'), report.get('optimizer_seed')) != RUNS[run] or report.get('budget') != 'long':
                raise ValueError('report run identity mismatch')
            if run in completed and (digest(report_path) != completed[run] or report.get('completed') is not True):
                raise ValueError('completed report mismatch')
            checkpoints = report.get('checkpoints')
            if not isinstance(checkpoints, list) or not checkpoints:
                raise DownloadError('initial checkpoint report not ready')
            seen = set()
            for row in checkpoints:
                step = row.get('step')
                if type(step) is not int or not 0 <= step <= 1024000 or step % 51200:
                    raise ValueError('invalid checkpoint step')
                relative = f'checkpoints/step-{step:09d}.zip'
                if row.get('path') != relative or relative in seen or not SHA.fullmatch(row.get('sha256', '')):
                    raise ValueError('invalid checkpoint path or SHA')
                seen.add(relative)
            metadata = retain_metadata(report_path, run)
            result['reports'].append(dict(run=run, sha256=digest(report_path), local_path=metadata,
                                           completed=report.get('completed', False)))
            for row in checkpoints:
                dest = output / run / row['path']
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or dest.is_symlink():
                    validate_zip(dest, row['sha256'])
                else:
                    temporary = staging / 'checkpoint.zip'
                    fetch(run + '/' + row['path'], temporary)
                    validate_zip(temporary, row['sha256'])
                    # Hard-link publication never replaces an existing checkpoint.
                    os.link(temporary, dest)
                    temporary.unlink()
                cp_receipt = dict(run=run, step=row['step'], sha256=row['sha256'],
                                  local_path=str(dest.relative_to(output)), zip_crc_passed=True,
                                  protocol_sha256=expected_protocol)
                receipt_path = dest.with_suffix('.receipt.json')
                if receipt_path.exists():
                    if json.loads(receipt_path.read_text()) != cp_receipt:
                        raise ValueError('immutable checkpoint receipt conflict')
                else:
                    with receipt_path.open('x') as stream:
                        json.dump(cp_receipt, stream, indent=2)
                result['checkpoints'].append(cp_receipt)
        result['job_status_local_path'] = retain_metadata(status_path, 'job-status')
        retain_metadata(remote_protocol, 'protocol')
        atomic(output / 'last-complete.json', result)
        return result


def watch(download, output, expected_protocol, *, poll_seconds=60, max_seconds=43200,
          clock=time.monotonic, sleep=time.sleep, once=False):
    if not math.isfinite(max_seconds) or not 0 < max_seconds <= 86400:
        raise ValueError('max_seconds must be positive and at most 86400')
    if not math.isfinite(poll_seconds) or poll_seconds < 60:
        raise ValueError('poll_seconds must be at least 60')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    deadline = clock() + max_seconds
    failures = 0
    last_complete = None
    def record(status, **extra):
        value = dict(status=status, consecutive_failures=failures, time_unix=time.time(),
                     last_complete_poll=last_complete, **extra)
        atomic(output / 'watch-status.json', value)
        with (output / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(value) + '\n')
        return value
    while clock() < deadline:
        try:
            result = poll(download, output, expected_protocol, deadline=deadline, clock=clock)
            failures = 0
            last_complete = result['observed_at_unix']
            if result['remote_status'] in ('completed', 'failed'):
                return record('remote_' + result['remote_status'])
            record('watching', checkpoint_count=len(result['checkpoints']))
            if once:
                return record('single_poll_complete')
            delay = poll_seconds
        except TimeoutError:
            return record('timeout')
        except Exception as error:
            failures += 1
            # Never persist arbitrary exception text or subprocess output.
            category = 'transport' if isinstance(error, DownloadError) else 'integrity_or_local_io'
            if failures >= 3:
                return record('failed', error_category=category)
            record('retrying', error_category=category)
            delay = 15 * 2 ** (failures - 1)
        sleep(max(0, min(delay, deadline - clock())))
    return record('timeout')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'runs/colab-filtered-joint-long-20261021-checkpoints')
    parser.add_argument('--state-file', type=Path, default=Path.home()/'.config/colab-cli/sessions.json')
    parser.add_argument('--poll-seconds', type=float, default=60)
    parser.add_argument('--max-seconds', type=float, default=43200)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    pins_path = Path(__file__).with_name('http-checkpoint-cli-pins.json')
    pins = json.loads(pins_path.read_text())
    def verify_pins():
        for name, expected in pins['files'].items():
            if digest(ROOT/name) != expected:
                raise ValueError('pinned CLI source changed')
    verify_pins()
    executable = ROOT/pins['executable']
    args.output.mkdir(parents=True, exist_ok=True)
    binding = dict(session=SESSION, protocol_sha256=EXPECTED_PROTOCOL, cli_pins_sha256=digest(pins_path))
    with (args.output/'watch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding_path = args.output/'binding.json'
        if binding_path.exists() and json.loads(binding_path.read_text()) != binding:
            raise ValueError('backup directory belongs to another binding')
        atomic(binding_path, binding)
        def download(remote, destination, timeout):
            verify_pins()
            download_cli(executable, args.state_file, SESSION, remote, destination, timeout)
        result = watch(download, args.output, EXPECTED_PROTOCOL, poll_seconds=args.poll_seconds,
                       max_seconds=args.max_seconds, once=args.once)
    print(json.dumps(result), flush=True)
    return 0 if result['status'] in ('remote_completed', 'single_poll_complete') else 1


if __name__ == '__main__':
    raise SystemExit(main())
