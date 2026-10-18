#!/usr/bin/env python3
"""Replay a trusted local balance or swing run with its verified archived evaluator.

Uses this Python environment without installing dependencies or accessing the
network. The archived evaluator retains its source/dependency/checkpoint guards.
The report binds recipe/source hashes; its own digest is recorded for replay,
not independently authenticated. No source guards are disabled or rewritten.
"""
import argparse
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_BYTES = 64 * 1024 * 1024
EVALUATORS = {'cartpole-balance-learning-v1': 'examples/balance_learning.py',
              'cartpole-swing-learning-v1': 'examples/swing_learning.py'}
REQUIRED_SOURCE = {
    'cartpole-balance-learning-v1': {'examples/balance_learning.py', 'src/cartpole_sdk/__init__.py',
                                  'src/cartpole_sdk/learning/balance_experiment.py'},
    'cartpole-swing-learning-v1': {'examples/swing_learning.py', 'src/cartpole_sdk/__init__.py',
                                'src/cartpole_sdk/learning/balance_experiment.py',
                                'src/cartpole_sdk/learning/swing_experiment.py'}}
EXTRA_SOURCE = {'pyproject.toml', 'README.md', 'uv.lock',
                'examples/balance_learning.py', 'examples/rl_diagnostics.py',
                'examples/swing_learning.py', 'scripts/swing-learning',
                'scripts/balance-learning', 'scripts/rl-diagnostics'}


def _read_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'expected regular input file: {path}')
    return path.read_bytes()


def _archive_members(archive, schema='cartpole-balance-learning-v1'):
    """Validate the whole snapshot before extracting any member."""
    members = archive.infolist()
    if not members or len(members) > 4096:
        raise ValueError('invalid archive member count')
    names, files, total = set(), set(), 0
    for member in members:
        name = member.filename
        parts = name.rstrip('/').split('/')
        if (name != member.orig_filename or not name.isascii() or
                '\\' in name or ':' in name or
                any(part in ('', '.', '..') for part in parts) or
                any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise ValueError(f'unsafe archive member path: {name!r}')
        key = name.rstrip('/').casefold()
        if key in names:
            raise ValueError(f'duplicate archive member: {name}')
        names.add(key)
        mode = stat.S_IFMT(member.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or (mode == stat.S_IFDIR) != member.is_dir() and mode:
            raise ValueError(f'unsafe archive member type: {name}')
        if member.flag_bits & 1 or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError(f'unsupported archive member encoding: {name}')
        total += member.file_size
        if member.file_size > MAX_MEMBER_BYTES or total > MAX_EXTRACTED_BYTES:
            raise ValueError('archive exceeds extraction size limits')
        path = PurePosixPath(name)
        package = len(parts) >= 2 and parts[:2] in (['src', 'cartpole_sdk'], ['src', 'cartpole_vision'])
        if member.is_dir():
            allowed = name.rstrip('/') in ('src', 'examples', 'scripts') or package
        else:
            allowed = name in EXTRA_SOURCE or (package and path.suffix == '.py') or (
                path.parent.as_posix() in ('src/cartpole_sdk/sim', 'src/cartpole_sdk/control')
                and path.suffix in ('.json', '.xml'))
            files.add(name)
        if not allowed:
            raise ValueError(f'unexpected archive member: {name}')
    if not REQUIRED_SOURCE[schema] <= files:
        family = 'swing' if schema == 'cartpole-swing-learning-v1' else 'balance'
        raise ValueError(f'archive lacks the frozen {family} evaluator')
    for name in files:
        if any(parent.as_posix() in files for parent in PurePosixPath(name).parents):
            raise ValueError('archive file/directory collision')
    return members


def replay(run, output, *, seeds, seconds=60., checkpoint=None, starts=('upright',)):
    """Run the archived CLI and add provenance beside its unchanged output."""
    run, output = Path(run).resolve(), Path(output).absolute()
    if os.path.lexists(output):
        raise FileExistsError(output)
    output = output.resolve()
    if (not seeds or any(type(seed) is not int or seed < 0 for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('distinct nonnegative evaluation seeds required')
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or
            not .01 <= seconds <= 60 or not math.isclose(seconds * 100, round(seconds * 100))):
        raise ValueError('seconds must contain whole 100 Hz decisions in .01..60')
    if not starts or len(set(starts)) != len(starts) or any(s not in ('upright', 'hanging') for s in starts):
        raise ValueError('unique upright/hanging starts required')
    if checkpoint is not None and (type(checkpoint) is not int or checkpoint < 0):
        raise ValueError('nonnegative checkpoint step required')
    raw_recipe, raw_report = (_read_file(run / name) for name in ('recipe.json', 'report.json'))
    recipe, report = json.loads(raw_recipe), json.loads(raw_report)
    schema = recipe.get('schema')
    if (schema not in EVALUATORS or
            sha256(raw_recipe).hexdigest() != report.get('recipe_sha256') or
            any(report.get(key) != value for key, value in recipe.items())):
        raise ValueError('recipe hash or report metadata mismatch')
    archive_path = run / 'source.zip'
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('source archive exceeds size limit')
    source = _read_file(archive_path)
    if sha256(source).hexdigest() != report.get('source_zip_sha256'):
        raise ValueError('source archive hash mismatch')
    evaluations = report.get('evaluations', [])
    selected = (evaluations[-1] if evaluations else None) if checkpoint is None else next(
        (row for row in evaluations if row.get('steps') == checkpoint), None)
    if selected is None:
        raise ValueError('checkpoint not found')
    cp = PurePosixPath(selected['checkpoint'])
    if (len(cp.parts) != 2 or cp.parts[0] != 'checkpoints' or cp.suffix != '.zip'
            or '\\' in str(cp) or (run / 'checkpoints').is_symlink()):
        raise ValueError('checkpoint path mismatch')
    checkpoint_path = run / cp
    checkpoint_sha = sha256(_read_file(checkpoint_path)).hexdigest()
    if checkpoint_sha != selected.get('checkpoint_sha256'):
        raise ValueError('checkpoint hash mismatch')
    pins = {run / 'recipe.json': sha256(raw_recipe).hexdigest(),
            run / 'report.json': sha256(raw_report).hexdigest(),
            archive_path: sha256(source).hexdigest(), checkpoint_path: checkpoint_sha}
    demonstration_sha = None
    if schema == 'cartpole-swing-learning-v1' and recipe['demonstrations'] is not None:
        demonstration_path = run / 'demonstrations.npz'
        demonstration_sha = sha256(_read_file(demonstration_path)).hexdigest()
        if (not isinstance(recipe['demonstrations'], dict) or
                demonstration_sha != recipe['demonstrations'].get('sha256')):
            raise ValueError('demonstration hash mismatch')
        pins[demonstration_path] = demonstration_sha
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        members = _archive_members(archive, schema)
        with tempfile.TemporaryDirectory(prefix='cartpole-balance-replay-') as directory:
            frozen = Path(directory).resolve()
            for member in members:
                destination = frozen / member.filename
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as stream:
                        stream.write(archive.read(member))
            command = [sys.executable, str(frozen / EVALUATORS[schema]),
                       'evaluate', str(run), '--output', str(output),
                       '--seeds', *map(str, seeds), '--seconds', str(float(seconds)),
                       '--starts', *starts]
            if checkpoint is not None:
                command += ['--checkpoint', str(checkpoint)]
            environment = dict(os.environ, PYTHONPATH=str(frozen / 'src'),
                               PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
            environment.pop('PYTHONHOME', None)
            subprocess.run(command, cwd=frozen, env=environment, check=True)
    if any(sha256(_read_file(path)).hexdigest() != pin for path, pin in pins.items()):
        raise ValueError('run inputs changed during replay; no success provenance written')
    evaluation = _read_file(output / 'evaluation.json')
    provenance = dict(schema='cartpole-balance-source-replay-v1', run=str(run),
        run_schema=schema, demonstrations_sha256=demonstration_sha,
        recipe_sha256=pins[run / 'recipe.json'], report_sha256=pins[run / 'report.json'],
        source_zip_sha256=pins[archive_path], checkpoint_sha256=checkpoint_sha,
        checkpoint_steps=selected['steps'], runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        python_executable=sys.executable, command=command, evaluation_sha256=sha256(evaluation).hexdigest(),
        seeds=list(seeds), seconds=float(seconds), starts=list(starts),
        source_provenance=recipe['provenance'], hardware_accepted=False, deployable=False,
        note='Archived evaluator and installed dependencies; original source guards remain enabled. Temporary source was removed.')
    with (output / 'replay-provenance.json').open('x') as stream:
        stream.write(json.dumps(provenance, indent=2, allow_nan=False) + '\n')
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--seconds', type=float, default=60.)
    parser.add_argument('--checkpoint', type=int)
    parser.add_argument('--starts', choices=('upright', 'hanging'), nargs='+', default=['upright'])
    args = parser.parse_args()
    try:
        replay(args.run, args.output, seeds=args.seeds, seconds=args.seconds,
               checkpoint=args.checkpoint, starts=args.starts)
    except subprocess.CalledProcessError as error:
        parser.exit(error.returncode if error.returncode > 0 else 1, 'archived evaluator failed\n')
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
