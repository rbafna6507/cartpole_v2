"""Data-only review must never fit a model or choose scored intervals."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest

def test_review_reports_admitted_source_and_nominal_conditions(tmp_path):
    pytest.importorskip('matplotlib')
    from test_collection_protocol import recorded_source
    from cartpole_sdk.identification.review import review_recording
    raw,p,_=recorded_source(tmp_path);out=tmp_path/'review'
    with patch('cartpole_sdk.identification.passive.fit_passive',side_effect=AssertionError('fit during blind review')):
        report=review_recording(raw,out)
    assert report['model_fitted'] is False and report['physical_model_validated'] is False
    assert report['collection_protocol']==p and report['state_count']>100
    assert (out/'raw-observations.png').stat().st_size>1000
    assert (out/'report.json').is_file()
    with pytest.raises(FileExistsError):review_recording(raw,out)

def test_review_failed_completion_does_not_create_output(tmp_path):
    from test_collection_protocol import recorded_source
    from cartpole_sdk.identification.review import review_recording
    raw,p,report=recorded_source(tmp_path);report['completed']=False
    (tmp_path/'report.json').write_text(json.dumps(report));out=tmp_path/'review'
    with pytest.raises(ValueError):review_recording(raw,out)
    assert not out.exists()
