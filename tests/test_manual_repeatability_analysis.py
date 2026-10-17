import importlib.util,json,math
from pathlib import Path
import numpy as np
import pytest

REPO=Path(__file__).resolve().parents[1]
SCRIPT=REPO/'evidence/system-id-20261017/tools/evaluate_manual_repeatability.py'
def tool():
    assert SCRIPT.exists(),'manual repeatability evaluator not implemented'
    spec=importlib.util.spec_from_file_location('manual_repeatability',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def example(fitter,coefficients,run='new-independent',initial=.5,duration=3.):
    q=math.pi-.11310915597373176+initial;w=0.;ts=np.arange(0,duration+.0001,.004);values=[q]
    for _ in ts[1:]:
        for __ in range(4):q,w=fitter.advance(q,w,.001,coefficients)
        values.append(q)
    return dict(run_id=run,episode_id='fixture',t_s=ts.tolist(),theta_rad=values)

def test_annotation_pin_is_checked_before_any_raw_input_read(tmp_path):
    m=tool();ann=tmp_path/'annotations.json';ann.write_text('{}')
    with pytest.raises(ValueError,match='annotation hash'):m.verify_annotation(ann,'0'*64)

def test_exact_frozen_coefficients_only_validation_no_refit():
    m=tool();fitter,training,freeze,ev=m.frozen_method(REPO);original=training['magnetic_reports']['viscous']['parameters'].copy();coeff=original['linear_coefficients'];ep=example(fitter,coeff)
    fitter.fit_passive=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('refit forbidden'))
    fitter.solve=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('solve forbidden'))
    result=m.score([ep],training['magnetic_reports']['viscous'],fitter,ev)
    assert result['aggregate']['parameters']==original and result['aggregate']['parameters_refitted'] is False
    assert result['per_episode'][0]['parameters']==original
    static=dict(ep,theta_rad=[math.pi-.11310915597373176]*len(ep['t_s']))
    rejected=m.score([static],training['magnetic_reports']['viscous'],fitter,ev)
    assert rejected['aggregate']['statistical_checks_pass'] is False
    assert rejected['aggregate']['parameters']==original

def test_continuous_mujoco_uses_one_past_only_initialization():
    pytest.importorskip('mujoco');m=tool();fitter,training,freeze,ev=m.frozen_method(REPO);p=freeze['candidate_parameters'];ep=example(fitter,p['linear_coefficients'])
    result=m.continuous(ep,p,REPO/'evidence/system-id-20261016/mujoco-passive-candidate/model-config.json')
    assert result['initial_t_s']==pytest.approx(.1)
    assert result['initial_velocity_support_s']==pytest.approx(.04)
    assert result['reset_count']==1 and result['force_saturated'] is False
    assert result['rmse_rad']<.01 and len(result['readings'])==len(ep['t_s'])-26
    altered=dict(ep,theta_rad=ep['theta_rad'][:26]+[x+.2 for x in ep['theta_rad'][26:]])
    again=m.continuous(altered,p,REPO/'evidence/system-id-20261016/mujoco-passive-candidate/model-config.json')
    assert again['initial_omega_rad_s']==result['initial_omega_rad_s']
    assert np.array(again['readings'])[:,2]==pytest.approx(np.array(result['readings'])[:,2])

def test_period_crossings_do_not_bridge_missing_samples():
    m=tool();t=np.arange(0,5,.0125);q=.5*np.sin(2*math.pi*t/.8)
    full=m.period_diagnostic(t,q)
    assert full['median_period_s']==pytest.approx(.8,abs=.001)
    keep=~((t>2.3)&(t<2.5));gapped=m.period_diagnostic(t[keep],q[keep])
    assert len(gapped['upward_crossings_s'])<len(full['upward_crossings_s'])
    assert not any(2.3<x<2.5 for x in gapped['upward_crossings_s'])

def test_secondary_candidate_pin_and_one_causal_ode_rollout():
    m=tool();fitter,training,freeze,ev=m.frozen_method(REPO);source=REPO/'evidence/system-id-20261017/analysis/passive-friction-diagnostics.json'
    with pytest.raises(ValueError,match='secondary candidate'):m.secondary_candidate(source,'0'*64)
    p=m.secondary_candidate(source,m.sha(source));ep=example(fitter,p['coefficients'])
    fitter.solve=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('refit forbidden'))
    r=m.continuous_ode(ep,p['coefficients'],fitter)
    assert r['reset_count']==1 and r['rmse_rad']<.01 and r['solver']=='frozen passive_fit.advance'
    altered=dict(ep,theta_rad=ep['theta_rad'][:26]+[q+.2 for q in ep['theta_rad'][26:]])
    again=m.continuous_ode(altered,p['coefficients'],fitter)
    assert np.array(r['readings'])[:,2]==pytest.approx(np.array(again['readings'])[:,2])

def test_camera_angle_coverage_is_interval_local_including_edge_loss():
    m=tool();r=m.observed_support([1.2,1.3],1.,2.,delivered=4)
    assert r['valid_fraction_of_delivered']==.5
    assert r['max_unobserved_gap_including_edges_s']==pytest.approx(.7)
    empty=m.observed_support([],1.,2.,delivered=3)
    assert empty['max_unobserved_gap_including_edges_s']==1.
    assert empty['valid_fraction_of_delivered']==0.

def test_display_branch_changes_only_integer_turn_not_frozen_phase():
    m=tool();q=np.array([-math.pi-.3,-math.pi+.2])
    origin=m.display_origin(q)
    assert origin==-math.pi
    assert q-origin==pytest.approx([-.3,.2])
    assert m.display_origin(q+2*math.pi)-origin==pytest.approx(2*math.pi)

def test_changed_simulator_source_rejected_before_rollout(tmp_path):
    m=tool()
    for name in ('backend.py','model.py','config.py'):(tmp_path/name).write_text('changed source')
    with pytest.raises(ValueError,match='frozen simulator source'):m.verify_simulator_sources(tmp_path)

def test_plot_handles_release_with_no_delivered_camera_frames(tmp_path):
    pytest.importorskip('matplotlib');m=tool();fitter,training,freeze,ev=m.frozen_method(REPO);p=freeze['candidate_parameters'];ep=example(fitter,p['linear_coefficients']);report=training['magnetic_reports']['viscous']
    r=dict(frozen_parameters=p,short_forecasts=m.score([ep],report,fitter,ev),short_forecast_readings=[dict(windows=m.forecast_readings(ep,p['linear_coefficients'],report['provenance']['config'],fitter))],continuous_rollouts=[m.continuous(ep,p,REPO/'evidence/system-id-20261016/mujoco-passive-candidate/model-config.json')],camera=dict(per_episode=[dict(geometry=dict(coverage=None))]))
    m.draw(r,[ep],tmp_path)
    assert (tmp_path/'camera-encoder-comparison.png').stat().st_size>1000
