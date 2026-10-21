#!/usr/bin/env python3
"""Prepare a new evidence-bound development training profile; offline only."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Repository containing the preserved source profiles and evidence.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--angle-source', choices=('raw', 'vision', 'fused'), default='raw')
    args = parser.parse_args(argv)
    try:
        from cartpole_sdk.learning.evidence_profile import build_evidence_training_bundle
        result = build_evidence_training_bundle(args.repo, args.output, angle_source=args.angle_source)
        print(json.dumps(dict(output=str(args.output), status=result['status'], hardware_accepted=False,
                              bundle_sha256=result['content_sha256'])))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'evidence training profile: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
