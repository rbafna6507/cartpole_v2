"""Batch evidence adapter: independent runs, immutable outputs, untouched fitter gates."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from cartpole_sdk.identification.fit import FitConfig, _segments, _windows

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'evidence/system-id-20261017/tools/analyze_pulse_batch.py'


def tool():
    spec=importlib.util.spec_from_file_location('pulse_batch_analysis',SCRIPT)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(tmp_path,sid,*,duration=3.65,invalid_index=None):
    directory=tmp_path/f'run-{sid}';directory.mkdir()
    path=directory/'rig-test.jsonl'
    rows=[dict(type='session',session=dict(session_id=str(sid),clock_id=f'board:{sid}')),
          dict(type='info',info=dict(sid=sid,firmware='executor-v6-measuredrail',encoder_upright_raw=330,
              home_epoch=14,reference_saved=True,encoder_conf_valid=True)),
          dict(type='ringdown_start',provenance=dict(sources={'identification/experiments.py':'a'*64}))]
    q=math.pi+.15+.01*sid;w=0.;h=.0005
    def accel(t):return .6*math.sin(2*math.pi*(.7+.01*sid)*t)+.4*math.sin(2*math.pi*1.3*t)
    def rhs(t,q,w):return w,9.81/.18*math.sin(q)-.65*w-accel(t)/.18*math.cos(q)
    for i in range(round(duration*100)+1):
        t=i/100
        rows.append(dict(type='state',state=dict(sid=sid,unwrapped_tick=10_000*sid+i*10,
            unwrapped_us=10_000_000*sid+i*10000,theta=q,angle_hat=q,omega=0.,acceleration=accel(t),
            demand=99.,mode=0 if i==invalid_index else 12,flags=207,fault=0,misses=0,
            received_ns=10_000_000_000+i*10_000_000)))
        for j in range(20):
            a,b=rhs(t+j*h,q,w);c,d=rhs(t+(j+.5)*h,q+h*a/2,w+h*b/2);q+=h*c;w+=h*d
    rows.append(dict(type='termination',error=None,records_dropped=0))
    save_source(path,rows)
    return path


def save_source(path,rows):
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (path.parent/'report.json').write_text(json.dumps(dict(schema='cartpole-id-run-v1',raw_log=path.name,
        raw_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),completed=True,
        stop_confirmed=True,records_dropped=0,camera={})))


def test_batch_time_shifts_preserve_deltas_and_fitter_run_boundaries(tmp_path):
    module=tool();training=[source(tmp_path,i) for i in range(1,5)];validation=[source(tmp_path,i) for i in (5,6)]
    batch=module.prepare_batch(training,validation)
    rows=batch['training']['rows'];inputs=batch['training']['inputs'];cfg=FitConfig()
    assert len(inputs)==4 and len(rows)==4*366
    segments=_segments(rows,'magnetic','commanded',cfg)
    assert len(segments)==4
    assert len(_windows(segments,0.,cfg)[1])>=cfg.min_windows
    for index,item in enumerate(inputs):
        subset=rows[index*366:(index+1)*366]
        assert len(_windows([segments[index]],0.,cfg)[1])<cfg.min_windows
        assert subset[-1]['t_s']-subset[0]['t_s']==pytest.approx(3.65)
        assert all(b['t_s']-a['t_s']==pytest.approx(.01) for a,b in zip(subset,subset[1:]))
        assert item['time_shift_s']==pytest.approx(subset[0]['t_s']-item['original_start_s'])
        assert item['identity']['collection_report']['completed'] is True
        assert all(r['run_id']==item['identity']['sha256'] for r in subset)
        assert all('omega_rad_s' not in r and r['acceleration_kind']=='commanded' for r in subset)
        if index:assert subset[0]['t_s']>rows[index*366-1]['t_s']+cfg.max_gap_s


@pytest.mark.parametrize('duplicate',('within_training','across_groups','same_session','same_clock'))
def test_batch_rejects_source_reuse_and_identity_overlap(tmp_path,duplicate):
    module=tool();a=source(tmp_path,1);b=source(tmp_path,2)
    if duplicate=='within_training':training=[a,a];validation=[b]
    elif duplicate=='across_groups':training=[a];validation=[a]
    else:
        rows=[json.loads(line) for line in b.read_text().splitlines()]
        if duplicate=='same_clock':rows[0]['session']['clock_id']='board:1'
        else:
            rows[0]['session']['session_id']='1';rows[1]['info']['sid']=1
            for row in rows:
                if row['type']=='state':row['state']['sid']=1
        save_source(b,rows);training=[a];validation=[b]
    with pytest.raises(ValueError,match='duplicate|overlap|independent'):module.prepare_batch(training,validation)


def test_invalid_rows_and_internal_gaps_remain_boundaries(tmp_path):
    module=tool();a=source(tmp_path,1,invalid_index=120);b=source(tmp_path,2)
    rows=[json.loads(line) for line in a.read_text().splitlines()]
    rows=[row for row in rows if not(row['type']=='state' and 11_800_000<=row['state']['unwrapped_us']<11_900_000)]
    save_source(a,rows);batch=module.prepare_batch([a],[b]);prepared=batch['training']['rows']
    assert sum(not row['valid'] for row in prepared)==1
    assert len(_segments(prepared,'magnetic','commanded',FitConfig()))==3
    assert len(prepared)==356


def test_failed_run_report_cannot_enter_batch(tmp_path):
    module=tool();a=source(tmp_path,1);b=source(tmp_path,2)
    report=json.loads((a.parent/'report.json').read_text());report['completed']=False;report['failure']='lease expired'
    (a.parent/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='collection report'):module.prepare_batch([a],[b])


def test_analysis_preserves_default_gates_canonical_sha_and_diagnostic_offset(tmp_path):
    module=tool();a=source(tmp_path,1);b=source(tmp_path,2)
    report=module.analyze([a],[b])
    assert not report['accepted'] and report['fit']['reasons']==('insufficient windows, rank or excitation',)
    assert report['fit']['provenance']['config']==vars(FitConfig())
    assert report['canonical_sha256']==module.digest(report['canonical_batches'])
    content=dict(report);pin=content.pop('content_sha256');assert pin==module.digest(content)
    assert report['recommended_for_hardware_rl'] is False
    assert report['input_semantics']['physical_cart_acceleration_measured'] is False
    shifted=module.analyze([a],[b],angle_offset_rad=-.1)
    assert shifted['angle_offset']['diagnostic_only'] is True
    assert shifted['fit']['provenance']['config']['angle_offset_rad']==-.1
    assert shifted['canonical_sha256']==report['canonical_sha256']


def test_cli_from_another_directory_preserves_rejection_and_never_overwrites(tmp_path):
    a=source(tmp_path,1);b=source(tmp_path,2);out=tmp_path/'batch.json'
    command=[sys.executable,str(SCRIPT),'--training',str(a),'--validation',str(b),'--output',str(out)]
    result=subprocess.run(command,cwd='/tmp',capture_output=True,text=True)
    assert result.returncode==2,result.stderr
    saved=out.read_bytes();report=json.loads(saved)
    assert report['accepted'] is False and report['fit']['reasons']
    again=subprocess.run(command,cwd='/tmp',capture_output=True,text=True)
    assert again.returncode==2 and out.read_bytes()==saved
    assert 'exists' in again.stderr


def test_renamed_and_time_shifted_measurement_copy_is_rejected(tmp_path):
    module=tool();a=source(tmp_path,1);b=source(tmp_path,2)
    rows=[json.loads(line) for line in a.read_text().splitlines()]
    rows[0]['session']=dict(session_id='2',clock_id='board:2');rows[1]['info']['sid']=2
    for row in rows:
        if row['type']=='state':
            row['state']['sid']=2;row['state']['unwrapped_us']+=10_000_000;row['state']['unwrapped_tick']+=10_000
    save_source(b,rows)
    with pytest.raises(ValueError,match='duplicate measurement'):module.prepare_batch([a],[b])


def test_aggregate_fit_uses_training_only_and_retains_default_validation_gates(tmp_path):
    module=tool();training=[source(tmp_path,i) for i in range(1,5)];validation=[source(tmp_path,i) for i in (5,6)]
    good=module.analyze(training,validation)
    assert good['fit']['training']['window_count']>=FitConfig().min_windows
    assert good['fit']['training']['segment_count']==4
    assert good['fit']['validation']['segment_count']==2
    assert good['fit']['validation']['prediction_windows']>=3
    assert good['fit']['parameters']['effective_length_m']==pytest.approx(.18,abs=.004)
    for path in validation:
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if row['type']=='state':row['state']['theta']+=.5
        save_source(path,rows)
    bad=module.analyze(training,validation)
    assert bad['fit']['parameters']==good['fit']['parameters']
    assert not bad['accepted'] and any('held-out' in r for r in bad['fit']['reasons'])
    assert bad['canonical_sha256']!=good['canonical_sha256']
    assert bad['fit']['provenance']['config']==vars(FitConfig())


@pytest.mark.parametrize('include_active_validation',(False,True))
def test_static_heldout_run_cannot_validate_dynamics_even_with_zero_prediction_error(tmp_path,include_active_validation):
    module=tool();training=[source(tmp_path,i) for i in range(1,5)];static=source(tmp_path,5)
    rows=[json.loads(line) for line in static.read_text().splitlines()]
    for row in rows:
        if row['type']=='state':row['state']['theta']=math.pi;row['state']['acceleration']=0.
    save_source(static,rows);validation=([source(tmp_path,6)] if include_active_validation else [])+[static]
    report=module.analyze(training,validation)
    assert report['fit']['accepted'] is True  # Reproduces the inherited aggregate fitter limitation.
    assert report['accepted'] is False
    checks=report['supplemental_validation']['per_run']
    assert len(checks)==len(validation)
    static_check=checks[-1]
    assert static_check['angle_span_rad']==0. and static_check['acceleration_std_m_s2']==0.
    assert static_check['passed'] is False
    assert any('validation excitation' in reason for reason in report['reasons'])
    assert report['supplemental_validation']['min_angle_span_rad']==FitConfig().min_angle_span_rad
    assert report['supplemental_validation']['min_acceleration_std_m_s2']==FitConfig().min_acceleration_rms_m_s2
