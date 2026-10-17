"""Saved-fit review must not refit, reselect validation, or alter admission."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from test_system_id_workflow import raw_recording


def api():
    assert importlib.util.find_spec('cartpole_sdk.identification.fit_review'), 'saved-fit review module missing'
    from cartpole_sdk.identification import fit_review
    return fit_review


@pytest.fixture
def fitted(tmp_path):
    from cartpole_sdk.identification.workflow import fit_passive_logs
    train=tmp_path/'train.jsonl';valid=tmp_path/'valid.jsonl'
    ta=raw_recording(train,71);va=raw_recording(valid,72,(.42,-.55,.65,-.7))
    report=fit_passive_logs(train,ta,valid,va)
    saved=tmp_path/'fit.json';saved.write_text(json.dumps(report))
    return saved,valid,va,report


def test_frozen_review_replays_saved_scores_without_refit_and_is_immutable(fitted,tmp_path):
    pytest.importorskip('matplotlib')
    m=api();saved,valid,ann,fit=fitted;out=tmp_path/'review'
    with patch('cartpole_sdk.identification.passive.fit_passive',side_effect=AssertionError('refit forbidden')):
        report=m.review_fit(saved,valid,ann,out,data_label='SYNTHETIC numerical verification')
    assert report['data_label']=='SYNTHETIC numerical verification'
    assert report['parameters_refitted'] is False
    assert report['solver']=='frozen passive ODE; not MuJoCo'
    assert report['saved_admission']['accepted']==fit['accepted']
    assert report['saved_admission']['reasons']==fit['reasons']
    assert report['parameters']==fit['parameters']
    assert report['short_forecasts']['prediction_rmse_rad']==pytest.approx(fit['validation']['prediction_rmse_rad'],abs=1e-12)
    assert len(report['episodes'])==4
    assert all(e['continuous']['prediction_samples']>0 for e in report['episodes'])
    assert (out/'recorded-vs-frozen-ode.png').stat().st_size>1000
    assert (out/'recorded-vs-frozen-ode.pdf').stat().st_size>1000
    assert (out/'report.json').exists()
    before=(out/'report.json').read_bytes()
    with pytest.raises(FileExistsError):m.review_fit(saved,valid,ann,out)
    assert (out/'report.json').read_bytes()==before


def test_rejected_fit_can_be_reviewed_without_promotion(fitted,tmp_path):
    pytest.importorskip('matplotlib')
    m=api();saved,valid,ann,fit=fitted
    fit.update(accepted=False,statistical_checks_pass=False,reasons=['preserved rejection'])
    saved.write_text(json.dumps(fit))
    result=m.review_fit(saved,valid,ann,tmp_path/'rejected')
    assert result['saved_admission']['accepted'] is False
    assert result['saved_admission']['reasons']==['preserved rejection']
    assert result['recommended_for_hardware_rl'] is False
    assert result['model_exported'] is False


@pytest.mark.parametrize('problem',('raw','annotations','reference','canonical','method','coefficient','driven'))
def test_changed_provenance_or_unsupported_fit_fails_before_output(fitted,tmp_path,problem):
    m=api();saved,valid,ann,fit=fitted
    if problem=='raw':valid.write_text(valid.read_text()+'\n')
    elif problem=='annotations':ann.write_text(ann.read_text()+'\n')
    elif problem=='reference':fit['provenance']['validation']['reference']=[999,*fit['provenance']['validation']['reference'][1:]]
    elif problem=='canonical':fit['provenance']['validation_sha256']='0'*64
    elif problem=='method':fit['provenance']['method_sha256']='0'*64
    elif problem=='coefficient':fit['parameters']['linear_coefficients'][0]=float('nan')
    elif problem=='driven':fit['kind']='driven'
    if problem not in ('raw','annotations'):saved.write_text(json.dumps(fit))
    out=tmp_path/'bad'
    with pytest.raises((ValueError,KeyError)):m.review_fit(saved,valid,ann,out)
    assert not out.exists()


def test_continuous_and_first_short_forecast_use_only_initial_past_samples():
    m=api()
    from cartpole_sdk.identification.passive import DEFAULT_GATES
    t=np.arange(0,1.704,.004);q=np.pi+.2*np.cos(7*t);cfg=dict(DEFAULT_GATES,window_s=.35)
    a=m.forecast_segment(t,q,[49.,.4,0.],cfg)
    changed=q.copy();changed[t>.101]+=np.sin(t[t>.101]*19)
    b=m.forecast_segment(t,changed,[49.,.4,0.],cfg)
    assert a['continuous']['initial']==b['continuous']['initial']
    assert a['continuous']['predicted_theta_rad']==b['continuous']['predicted_theta_rad']
    assert a['short_windows'][0]['predicted_theta_rad']==b['short_windows'][0]['predicted_theta_rad']
    assert a['continuous']['initial']['support_end_s']==pytest.approx(.1)
