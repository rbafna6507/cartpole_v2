#!/usr/bin/env python3
"""Reuse frozen HTTP-only backup validation with an explicit new session/output."""
import importlib.util
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
path=HERE.parent/'combined-next/http_checkpoint_watch.py'
spec=importlib.util.spec_from_file_location('original_http_watch',path)
watch=importlib.util.module_from_spec(spec);spec.loader.exec_module(watch)
watch.SESSION='filtered-bal-joint-recovery-20261021'
if __name__=='__main__':
    raise SystemExit(watch.main(['--output',str(watch.ROOT/'runs/colab-filtered-joint-recovery-20261021-checkpoints'),*sys.argv[1:]]))
