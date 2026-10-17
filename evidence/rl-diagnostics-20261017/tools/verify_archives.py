#!/usr/bin/env python3
"""Verify archived files against their hashes, without extracting or loading models."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'archive-manifest.json').read_text())
count = 0
for name, spec in manifest['archives'].items():
    path = root / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256'], name
    with tarfile.open(path, 'r:xz') as archive:
        members = {m.name: m for m in archive.getmembers()}
        assert set(members) == set(spec['members']), name
        for rel, expected in spec['members'].items():
            assert members[rel].isfile(), rel
            assert hashlib.sha256(archive.extractfile(members[rel]).read()).hexdigest() == expected, rel
            count += 1
for rel, expected in {**manifest['supplements'], **manifest.get('standalone', {})}.items():
    assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == expected, rel
assert hashlib.sha256((root / 'tools/frozen_teacher_probe.py').read_bytes()).hexdigest() == manifest['frozen_teacher_script_sha256']
print(f'Verified {count} archived files, runtime supplements and frozen teacher script.')
