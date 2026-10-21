"""Local fixed-model prediction and evidence admission; no rig/network access."""
import importlib
import json
import math
from dataclasses import replace

import numpy as np
import pytest

from cartpole_sdk.identification import campaign


def module():
    return importlib.import_module('cartpole_sdk.identification.driven_validation')


def make_campaign(path, *, role='validation', partial=False, gap=False):
    path.mkdir();origin=1_000_000_000_000;rows=[];states=[]
    for i in range(451):
        if gap and i==170:continue
        t=i/100;ns=origin+round(t*1e9)
        active=100<=i<400
        state=dict(sid=7,tick=i*10,unwrapped_us=100_000_000+i*10000,received_ns=ns+1000000,
                   mode=12 if active else 0,flags=207 if active else 205,fault=0,
                   theta=math.pi+.2*math.cos(8*t),omega=-1.6*math.sin(8*t),
                   x=0.,velocity=0.,acceleration=.1*math.sin(6*t),misses=0,dropped=0)
        states.append(state);rows.append(dict(type='state',host_monotonic_ns=ns+1000000,state=state))
    rows.extend([dict(type='driven_start',host_monotonic_ns=origin+990_000_000,
                      initial_hanging=math.pi-.06,procedure='actuator',seconds=3.),
                 dict(type='driven_stop',host_monotonic_ns=origin+4_010_000_000,confirmed=True)])
    rows.sort(key=lambda r:r['host_monotonic_ns'])
    trials=[dict(id='001-actuator',kind='actuator',started_ns=origin+500_000_000,
                 finished_ns=origin+4_400_000_000,completed=True,
                 trial=dict(kind='pulse',amplitude_m=.01,segment_s=.4,hold_s=3.),
                 result=dict(completed=True,policy=dict(clamped_commands=0)))]
    if partial:
        trials.append(dict(id='002-actuator',kind='actuator',started_ns=origin+5_000_000_000,
                           finished_ns=origin+5_100_000_000,completed=False,failure='ACTION_EXPIRED'))
    (path/'rig.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    report=dict(schema=campaign.SCHEMA,synthetic=False,completed=not partial,stop_confirmed=not partial,
                dataset_role=role,raw_log='rig.jsonl',records_dropped=0,pending_log_records=0,
                sensor_mode='encoder_only',trials=trials,
                failure='ACTION_EXPIRED' if partial else None)
    (path/'report.json').write_text(json.dumps(report));campaign.seal(path)
    return path


def test_causal_rate_uses_only_history_at_forecast_start():
    m=module();t=np.arange(0,1,.01);q=3+2*t+4*t*t;i=30
    rate=m.causal_encoder_rate(t,q,i)
    assert rate==pytest.approx(2+8*t[i],abs=1e-10)
    q[i+1:]+=100
    assert m.causal_encoder_rate(t,q,i)==rate


def test_known_acceleration_equilibrium_checks_force_sign_and_phase():
    m=module();model=m.FrozenDrivenModel();a=.5;offset=-.06
    q=math.pi+math.atan(a/model.gravity_m_s2)
    t=np.arange(0,3.01,.01)
    result=m.score_trajectory(t,np.full(len(t),q+offset),np.full(len(t),a),np.zeros(len(t)),
                              model=model,phase_offset_rad=offset)
    assert result['causal_encoder']['prediction_rmse_rad']<1e-10
    assert result['recorded_omega']['prediction_rmse_rad']<1e-10
    assert result['forecast_checks_pass'] is False  # static data cannot validate dynamics


def test_recorded_omega_is_comparator_and_cannot_replace_causal_primary():
    m=module();t=np.arange(0,3.01,.01);q=math.pi+.2*np.cos(8*t);a=np.zeros(len(t))
    good=m.score_trajectory(t,q,a,-1.6*np.sin(8*t))
    bad=m.score_trajectory(t,q,a,np.full(len(t),20.))
    assert good['causal_encoder']==bad['causal_encoder']
    assert good['recorded_omega']['prediction_rmse_rad']!=bad['recorded_omega']['prediction_rmse_rad']


def test_independent_forced_pendulum_matches_fixed_law_without_fitting():
    m=module();model=m.FrozenDrivenModel();t=np.arange(0,3.01,.01)
    inputs=.4*np.sin(2*math.pi*1.2*t);q=math.pi+.2;w=0.;angles=[q];rates=[w]
    # Independent midpoint scheme at0.1ms with left-held forcing; no call to advance.
    def force(angle,rate,a):
        return ((model.gravity_m_s2*math.sin(angle)-a*math.cos(angle))/model.effective_length_m-
                model.angular_damping_per_s*rate-model.coulomb_rad_s2*math.tanh(rate/.05))
    for a in inputs[:-1]:
        for _ in range(100):
            qm=q+.00005*w;wm=w+.00005*force(q,w,a)
            q+=.0001*wm;w+=.0001*force(qm,wm,a)
        angles.append(q);rates.append(w)
    scored=m.score_trajectory(t,angles,inputs,rates)
    assert scored['recorded_omega']['prediction_rmse_rad']<1e-5
    assert scored['causal_encoder']['prediction_rmse_rad']<.01


@pytest.mark.parametrize('change',['reverse','duplicate','gap','nan'])
def test_trajectory_continuity_fails_closed(change):
    m=module();t=np.arange(0,3.01,.01);q=math.pi+.2*np.cos(8*t)
    if change=='reverse':t[25]=t[24]-.001
    elif change=='duplicate':t[25]=t[24]
    elif change=='gap':t[25:]+=.01
    else:q[25]=np.nan
    with pytest.raises(ValueError):m.score_trajectory(t,q,np.zeros(len(t)),np.zeros(len(t)))


def test_command_input_is_left_held_without_future_sample_leak():
    m=module();model=replace(m.FrozenDrivenModel(),coulomb_rad_s2=0.)
    # At upright q=0, a positive input causes negative angular acceleration.
    q,w=m.advance(0.,0.,.01,0.,model)
    assert q==0 and w==0
    assert m.advance(0.,0.,.01,1.,model)[0]<0
    t=np.arange(0,1.01,.01);angle=np.full(len(t),math.pi)
    a=np.zeros(len(t));a[20]=10.
    r=m.score_trajectory(t,angle,a,np.zeros(len(t)),start_index=19,model=model)
    first=r['windows'][0]['points'][0]
    assert first['t_s']==pytest.approx(.20)
    assert first['causal_encoder_prediction_rad']==pytest.approx(math.pi,abs=1e-12)


def test_roles_sources_and_local_phase_sensitivity_are_explicit(tmp_path):
    m=module();source=make_campaign(tmp_path/'validation')
    result=m.analyze_driven_campaigns(validation_dirs=[source],plot=False)
    run=result['validation'][0];trial=run['trials'][0]
    assert run['declared_dataset_role']=='validation'
    assert run['source_raw_sha256'] and run['source_manifest_sha256']
    assert trial['phase_baselines']['firmware_reference']['phase_offset_rad']==0.
    assert trial['phase_baselines']['local_hanging_anchor']['phase_offset_rad']==pytest.approx(-.06)
    assert result['parameters_fitted'] is False
    assert result['hardware_accepted'] is False
    assert result['physical_acceleration_measured'] is False
    assert 'recorded_omega' in trial['phase_baselines']['firmware_reference']['scores']
    with pytest.raises(ValueError,match='role'):
        m.analyze_driven_campaigns(training_dirs=[source],plot=False)
    with pytest.raises(ValueError,match='duplicate'):
        m.analyze_driven_campaigns(validation_dirs=[source,source],plot=False)


def test_seal_mutation_and_synthetic_source_rejected(tmp_path):
    m=module();source=make_campaign(tmp_path/'source')
    with (source/'rig.jsonl').open('a') as f:f.write('{}\n')
    with pytest.raises(ValueError,match='integrity'):
        m.analyze_driven_campaigns(validation_dirs=[source],plot=False)
    fake=make_campaign(tmp_path/'synthetic');report=json.loads((fake/'report.json').read_text())
    report['synthetic']=True;(fake/'report.json').write_text(json.dumps(report))
    (fake/'manifest.json').unlink();campaign.seal(fake)
    with pytest.raises(ValueError,match='synthetic'):
        m.analyze_driven_campaigns(validation_dirs=[fake],plot=False)


@pytest.mark.parametrize('problem',['fault','counter','session','duplicate'])
def test_corrupt_scored_support_cannot_satisfy_forecast_checks(tmp_path,problem):
    m=module();source=make_campaign(tmp_path/'bad');rows=[json.loads(x) for x in (source/'rig.jsonl').read_text().splitlines()]
    index=next(i for i,r in enumerate(rows) if r.get('type')=='state' and r['state']['tick']==2000)
    if problem=='fault':rows[index]['state']['fault']=1
    elif problem=='counter':rows[index]['state']['dropped']=1
    elif problem=='session':rows[index]['state']['sid']=8
    else:
        altered=json.loads(json.dumps(rows[index]));altered['state']['theta']+=.1;rows.insert(index+1,altered)
    (source/'rig.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows));(source/'manifest.json').unlink();campaign.seal(source)
    run=m.analyze_driven_campaigns(validation_dirs=[source],plot=False)['validation'][0]
    assert run['trials'][0]['status']=='rejected_continuity_or_admission'


def test_partial_campaign_requires_explicit_diagnostics_and_preserves_failure(tmp_path):
    m=module();source=make_campaign(tmp_path/'partial',partial=True)
    with pytest.raises(ValueError,match='partial'):
        m.analyze_driven_campaigns(validation_dirs=[source],plot=False)
    r=m.analyze_driven_campaigns(validation_dirs=[source],allow_partial=True,plot=False)
    run=r['validation'][0]
    assert run['partial_diagnostics'] is True
    assert run['trials'][0]['status']=='scored'
    assert run['trials'][1]['status']=='excluded_incomplete'
    assert run['trials'][1]['failure']=='ACTION_EXPIRED'
    assert r['hardware_accepted'] is False


def test_gap_rejects_trial_instead_of_interpolating_it(tmp_path):
    m=module();source=make_campaign(tmp_path/'gapped',gap=True)
    run=m.analyze_driven_campaigns(validation_dirs=[source],plot=False)['validation'][0]
    assert run['trials'][0]['status']=='rejected_continuity_or_admission'
    assert 'gap' in run['trials'][0]['reason']


def test_output_cannot_mutate_sealed_input_or_overwrite_previous_results(tmp_path):
    m=module();source=make_campaign(tmp_path/'source')
    with pytest.raises(ValueError,match='outside'):
        m.analyze_driven_campaigns(validation_dirs=[source],output=source/'analysis',plot=False)
    out=tmp_path/'out';result=m.analyze_driven_campaigns(validation_dirs=[source],output=out,plot=False)
    assert json.loads((out/'analysis.json').read_text())==result
    assert campaign.verify(source)==(True,None)
    with pytest.raises(FileExistsError):
        m.analyze_driven_campaigns(validation_dirs=[source],output=out,plot=False)
