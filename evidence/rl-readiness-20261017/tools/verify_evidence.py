#!/usr/bin/env python3
"""Verify archived cart collection, immutable profiles and frozen replay metrics offline."""
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((HERE/'cart-data/sources.json').read_text())
    archive=HERE/'cart-data/raw-recordings.tar.xz'
    assert sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    reports=[]
    with tarfile.open(archive) as source:
        for name,pin in manifest['sources'].items():
            raw=source.extractfile(name).read()
            assert sha256(raw).hexdigest()==pin,name
            if name.endswith('/report.json'):reports.append(json.loads(raw))
    assert len(reports)==6 and len([r for r in reports if r['procedure']=='pulse'])==5
    parameters=[r['result']['parameters'] for r in reports]
    assert all(p==parameters[0] for p in parameters)
    for r in reports:
        assert r['completed'] and r['stop_confirmed'] and r['records_dropped']==0
        assert r['stop_state']['mode']==0 and not(r['stop_state']['flags']&2) and r['stop_state']['fault']==0
        assert r['result']['info']['encoder_upright_raw']==330
        assert r['result']['info']['home_epoch']==15
        assert r['result']['info']['i2c_errors']==5
        if r['procedure']=='pulse':assert r['result']['policy']['clamped_commands']==0
    report=json.loads((HERE/'cart-analysis/report.json').read_text())
    freeze=ROOT/'evidence/system-id-model-review-20261017/candidate-freeze-latest6.json'
    assert report['freeze_sha256']==sha256(freeze.read_bytes()).hexdigest()
    assert report['parameters_fitted'] is False and report['hardware_accepted'] is False
    errors=[]
    for row in report['runs']:
        tr=row['angle_trace']
        err=[math.degrees(math.atan2(math.sin(p-m),math.cos(p-m))) for p,m in zip(tr['predicted_rad'],tr['measured_rad'])]
        assert math.isclose(math.sqrt(sum(x*x for x in err)/len(err)),row['replay_angle_deg']['rms'],abs_tol=1e-10)
        assert row['force_saturated_ticks']==0
        errors.extend(err)
    assert len(errors)==report['continuous_angle_deg']['samples']
    assert math.isclose(math.sqrt(sum(x*x for x in errors)/len(errors)),report['continuous_angle_deg']['rms'],abs_tol=1e-10)
    for mode in ('encoder','vision','fused'):
        profile=ROOT/f'training/profiles/rl-{mode}-20261017'
        manifest=json.loads((profile/'bundle.json').read_text())
        for name,pin in manifest['files_sha256'].items():assert sha256((profile/name).read_bytes()).hexdigest()==pin
        config=json.loads((profile/'observation-config.json').read_text())
        assert config['angle_source']==('raw' if mode=='encoder' else mode)
        assert config['vision_dropout_probability']==0
    print(json.dumps(dict(passed=True,cart_runs=5,inspection_runs=1,profiles=3,parameters_unchanged=True,
        recorded_final_disabled=True,pooled_angle_rms_deg=report['continuous_angle_deg']['rms'])))

if __name__=='__main__':main()
