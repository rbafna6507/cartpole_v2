"""Focused numerical checks for the offline saved-forecast audit."""

import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def audit():
    path = Path(__file__).with_name("audit_forecast_horizons.py")
    assert path.exists(), "offline horizon audit has not been implemented"
    spec = importlib.util.spec_from_file_location("audit_forecast_horizons", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def window(start=0.0):
    return {
        "start_s": start,
        "end_s": start + 0.5,
        "initial_encoder_angle_rad": 0.0,
        "causal_initial_omega_rad_s": 1.0,
        "recorded_initial_omega_rad_s": 0.5,
        "points": [
            {
                "t_s": start + i / 100,
                "phase": "native_mode_3",
                "measured_encoder_rad": 0.0,
                "causal_encoder_prediction_rad": i / 100,
                "causal_encoder_error_rad": i / 100,
                "recorded_omega_prediction_rad": i / 50,
                "recorded_omega_error_rad": i / 50,
            }
            for i in range(1, 51)
        ],
    }


def test_exact_lead_is_not_prefix_rms_and_initializers_remain_separate(audit):
    result = audit.audit_windows([window()])
    causal = result["initializers"]["causal_encoder"]
    recorded = result["initializers"]["recorded_omega"]
    assert causal["exact_lead"]["50"]["rmse_rad"] == pytest.approx(0.05)
    assert causal["pooled_prefix"]["50"]["rmse_rad"] == pytest.approx(0.033166247903554)
    assert causal["exact_lead"]["50"]["sample_count"] == 1
    assert causal["pooled_prefix"]["50"]["sample_count"] == 5
    assert recorded["exact_lead"]["50"]["rmse_rad"] == pytest.approx(0.1)
    assert recorded["pooled_prefix"]["50"]["rmse_rad"] == pytest.approx(0.066332495807108)


def test_phase_selection_uses_whole_windows_and_keeps_identical_origins(audit):
    mixed = window(2.0)
    mixed["points"][-1]["phase"] = "native_mode_2"
    result = audit.audit_windows([window(), mixed, window(4.0)])
    assert result["source_window_count"] == 3
    assert result["selected_window_count"] == 2
    assert [origin["start_s"] for origin in result["origins"]] == [0.0, 4.0]
    for initializer in result["initializers"].values():
        assert [initializer["exact_lead"][str(h)]["sample_count"]
                for h in (10, 50, 100, 200, 500)] == [2, 2, 2, 2, 2]
        assert [initializer["pooled_prefix"][str(h)]["sample_count"]
                for h in (10, 50, 100, 200, 500)] == [2, 10, 20, 40, 100]


def test_missing_lead_and_inconsistent_saved_error_are_rejected(audit):
    missing = window()
    del missing["points"][4]
    with pytest.raises(ValueError, match="exact lead"):
        audit.audit_windows([missing])
    inconsistent = copy.deepcopy(window())
    inconsistent["points"][0]["causal_encoder_error_rad"] = 0.2
    with pytest.raises(ValueError, match="circular residual"):
        audit.audit_windows([inconsistent])


def test_source_hash_mismatch_is_rejected_before_analysis(audit):
    with pytest.raises(ValueError, match="source hash"):
        audit.validate_source({"analysis_source_sha256": "0" * 64}, b"changed source")
