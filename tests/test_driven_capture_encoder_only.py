"""Explicit camera omission leaves motion guards and STOP behavior intact."""
from dataclasses import replace
import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.identification import driven_capture as driven
from test_id_driven_capture import setup_rig, clocks, assert_stopped


@pytest.mark.parametrize('operation', ['timing','actuator','coupled','return'])
def test_missing_camera_requires_explicit_encoder_only_mode(operation):
    for encoder_only in (False, True):
        rig, clock, _ = setup_rig()
        kwargs=dict(camera=None,encoder_only=encoder_only,expected_reference=330,expected_home=14)
        def run():
            if operation=='timing':return driven.run_timing_hold(rig,seconds=1.,**kwargs)
            if operation=='actuator':return driven.run_actuator(rig,trial=driven.actuator_plan()[0],**kwargs)
            if operation=='coupled':return driven.run_coupled(rig,seconds=1.,**kwargs)
            return driven.return_saved_home(rig,**kwargs)
        with clocks(clock):
            if encoder_only:
                result=run()
                assert result['sensor_mode']=='encoder_only'
                assert result['camera_quality']['recorded'] is False
                assert result['camera_quality']['physical_tracking_proven'] is False
            else:
                with pytest.raises(ValidationError,match='camera'):run()
                assert not any(c[1] in ('ARM','MODE','REHOME') for c in rig.commands)
        assert_stopped(rig)


@pytest.mark.parametrize('fault', ['rail','switch','home','reference','stale'])
def test_encoder_only_still_rejects_unsafe_or_stale_state_before_arm(fault):
    rig, clock, _ = setup_rig()
    if fault=='rail':rig._state=replace(rig._state,x=.2)
    if fault=='switch':rig._state=replace(rig._state,flags=rig._state.flags|16)
    if fault=='home':rig._info.home_epoch=15
    if fault=='reference':rig._info.encoder_upright_raw=331
    if fault=='stale':
        original=rig.get_parameters
        def delayed_parameters():
            values=original()
            clock.now_ns+=200_000_000
            return values
        rig.get_parameters=delayed_parameters
    with clocks(clock),pytest.raises(ValidationError):
        driven.run_timing_hold(rig,seconds=1.,camera=None,encoder_only=True,
                              expected_reference=330,expected_home=14)
    assert_stopped(rig)
    assert not any(c[1] in ('ARM','MODE','REHOME') for c in rig.commands)
