import math
import json
import numpy as np
import pytest
from cartpole_sdk.identification import FitConfig, identify_pendulum, read_rows


def trial(run, phase=0., noise=.0003, gap=False, length=.32, gain=.87, damping=.12, delay=.03):
    rng = np.random.default_rng(100 + int(phase * 10))
    dt = .005
    theta, omega = math.pi + .65, .1
    def accel(t):
        return 1.2 * math.sin(2.7*t+phase) + .8 * math.sin(5.9*t+.3+phase) + .3*math.sin(9.1*t)
    def derivative(t, state):
        q, w = state
        return np.array([w, 9.81/length*math.sin(q)-damping*w-gain/length*accel(t-delay)*math.cos(q)])
    rows = []
    for i in range(4001):
        t = i*dt
        rows.append(dict(t_s=t, theta_rad=math.atan2(math.sin(theta), math.cos(theta))+rng.normal(0, noise),
                         omega_rad_s=float(omega), cart_acceleration_m_s2=accel(t), valid=not (gap and 8<t<8.3),
                         run_id=run, calibration_id='fixed', source='magnetic', acceleration_kind='commanded'))
        y = np.array([theta, omega]); a=derivative(t,y); b=derivative(t+dt/2,y+dt*a/2)
        c=derivative(t+dt/2,y+dt*b/2); d=derivative(t+dt,y+dt*c)
        theta, omega = y + dt*(a+2*b+2*c+d)/6
    return rows


def test_recovers_nonlinear_physics_noise_and_gaps_with_independent_prediction():
    fit = identify_pendulum(trial('train', gap=True), trial('holdout', phase=1.1))
    assert fit.accepted, fit.to_dict()
    assert fit.parameters['effective_length_m'] == pytest.approx(.32, rel=.03)
    assert fit.parameters['input_gain'] == pytest.approx(.87, rel=.06)
    assert fit.parameters['angular_damping_per_s'] == pytest.approx(.12, abs=.05)
    assert fit.parameters['delay_s'] == pytest.approx(.03, abs=.011)
    assert fit.validation['prediction_rmse_rad'] < .025
    assert fit.training['segment_count'] == 2
    assert len(fit.provenance['training_sha256']) == 64
    assert 'cart_mass_kg' in fit.unidentifiable
    json.dumps(fit.to_dict(), allow_nan=False)


def test_no_excitation_cannot_produce_an_accepted_fit():
    rows = [dict(t_s=i*.01, theta_rad=math.pi, cart_acceleration_m_s2=0., run_id='train') for i in range(501)]
    holdout = [dict(r, run_id='test') for r in rows]
    fit=identify_pendulum(rows, holdout)
    assert not fit.accepted
    assert any('rank' in x or 'excitation' in x for x in fit.reasons)
    assert fit.recommended_model is None


def test_separate_inputs_cannot_reuse_the_training_run():
    rows=trial('same')
    with pytest.raises(ValueError, match='independent|overlap'):
        identify_pendulum(rows, [dict(r) for r in rows])


@pytest.mark.parametrize('key,value', [('t_s', float('nan')), ('theta_rad', float('inf')), ('cart_acceleration_m_s2', float('nan'))])
def test_rejects_nonfinite_measurements(key,value):
    rows=trial('train'); rows[10][key]=value
    with pytest.raises(ValueError, match='finite'):
        identify_pendulum(rows, trial('test', phase=1.1))


def test_source_and_clock_guards():
    rows=trial('train'); rows[40]['t_s']=rows[39]['t_s']
    with pytest.raises(ValueError, match='increase'):
        identify_pendulum(rows, trial('test'))
    rows=trial('train'); rows[40]['acceleration_kind']='measured'
    with pytest.raises(ValueError, match='acceleration_kind'):
        identify_pendulum(rows, trial('test'))


def test_bad_heldout_plant_rejects_recommendation():
    fit=identify_pendulum(trial('train'), trial('test', phase=1.1, length=.5))
    assert not fit.accepted
    assert fit.recommended_model is None
    assert any('held-out' in r for r in fit.reasons)


def test_csv_column_mapping_is_explicit(tmp_path):
    path=tmp_path/'input.csv'; path.write_text('seconds,angle,command\n0,3.14,0\n.01,3.13,1\n')
    with pytest.raises(ValueError, match='columns'):
        read_rows(path, format='csv')
    rows=read_rows(path, format='csv', columns={'t_s':'seconds','theta_rad':'angle','cart_acceleration_m_s2':'command'})
    assert rows[1]['cart_acceleration_m_s2'] == 1.


def test_integral_fit_is_invariant_to_full_turn_offset_and_irregular_sampling():
    rows=trial('train',noise=0.);validation=trial('test',phase=1.1,noise=0.)
    rows=[r for i,r in enumerate(rows) if i%7 not in (2,5)]
    first=identify_pendulum(rows,validation)
    shifted=[dict(r,theta_rad=r['theta_rad']+2*math.pi) for r in rows]
    second=identify_pendulum(shifted,validation)
    assert second.parameters['effective_length_m']==pytest.approx(first.parameters['effective_length_m'],abs=1e-8)
    assert second.parameters['effective_length_m']==pytest.approx(.32,rel=.03)


def test_angle_only_prediction_and_calibration_segments():
    rows=trial('train',gap=True);validation=trial('test',phase=1.1)
    for r in rows:
        r.pop('omega_rad_s')
        if r['t_s']>12:r['calibration_id']='new'
    for r in validation:r.pop('omega_rad_s')
    fit=identify_pendulum(rows,validation)
    assert fit.accepted,fit.to_dict()
    assert fit.training['segment_count']==3


def test_unphysical_negative_damping_rejected():
    fit=identify_pendulum(trial('train',damping=-.1),trial('test',phase=1.1,damping=-.1))
    assert not fit.accepted
    assert any('damping' in r for r in fit.reasons)


def test_copied_rows_with_renamed_run_cannot_pass_independence_guard():
    rows=trial('train')
    fit=identify_pendulum(rows,[dict(r,run_id='renamed-copy') for r in rows])
    assert not fit.accepted
    assert any('identical' in reason for reason in fit.reasons)


def test_sdk_run_adapter_requires_matching_clock_and_effective_acceleration_time():
    from cartpole_sdk.identification import sdk_run_rows
    kwargs=dict(angle_channel={'entity':'pole','quantity':'angle','source':'magnetic','frame_id':'rig'},
                acceleration_kind='commanded',acceleration_field='cmd',time_field='t_ns',time_scale_s=1e-9,
                run_id='trial',calibration_id='home',clock_id='board-mapped')
    record=dict(t_ns=1_000_000_000,cmd=1.3,observation={'clock_id':'board-mapped','samples':[
        dict(entity='pole',quantity='angle',source='magnetic',frame_id='rig',unit='rad',value=.4,validity='valid',effective_ns=1_000_000_000)]})
    result=sdk_run_rows([record],**kwargs)
    assert result[0]['theta_rad']==.4
    assert result[0]['acceleration_kind']=='commanded'
    record['t_ns']+=10_000_000
    with pytest.raises(ValueError,match='effective time mismatch'):
        sdk_run_rows([record],**kwargs)


def test_cli_writes_reviewable_report_for_distinct_files(tmp_path):
    import subprocess
    import sys
    train=tmp_path/'train.jsonl';valid=tmp_path/'valid.jsonl';out=tmp_path/'fit.json'
    for path,rows in ((train,trial('train')),(valid,trial('test',phase=1.1))):
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    completed=subprocess.run([sys.executable,'examples/identify.py','--training',str(train),'--validation',str(valid),
                              '--format','rows-jsonl','--acceleration-kind','commanded','--output',str(out)],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    report=json.loads(out.read_text())
    assert report['accepted']
    assert report['provenance']['training_file_sha256']!=report['provenance']['validation_file_sha256']


def test_derivative_effective_time_must_be_aligned_explicitly():
    rows=trial('train')
    rows[100]['omega_effective_t_s']=rows[100]['t_s']-.03
    with pytest.raises(ValueError,match='omega.*effective'):
        identify_pendulum(rows,trial('test',phase=1.1))


def test_angle_zero_bias_cannot_be_absorbed_into_physical_parameters():
    from dataclasses import replace
    train=[dict(r,theta_rad=r['theta_rad']+.13) for r in trial('train')]
    valid=[dict(r,theta_rad=r['theta_rad']+.13) for r in trial('test',phase=1.1)]
    report=identify_pendulum(train,valid)
    assert not report.accepted
    assert any('zero' in reason for reason in report.reasons)
    assert report.training['angle_zero_diagnostic']['gravity_offset_rad']==pytest.approx(.13,abs=.02)
    calibrated=identify_pendulum(train,valid,config=replace(FitConfig(),angle_offset_rad=.13))
    assert calibrated.accepted,calibrated.to_dict()
    assert calibrated.parameters['effective_length_m']==pytest.approx(.32,rel=.03)
