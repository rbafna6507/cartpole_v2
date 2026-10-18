"""Disabled manual capture: observed data, independent labels, and bounded input."""
from contextlib import contextmanager
from dataclasses import replace
import json
import math
import os
import threading
from unittest.mock import patch

import pytest

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.identification import experiments
from test_passive_collection_baseline import camera_reader
from test_system_id_experiments import scripted_rig


@contextmanager
def session():
    from cartpole_sdk.identification import manual_capture
    rig, clock = scripted_rig()
    class Camera:
        checks = 0
        def check(self):
            self.checks += 1
        def latest(self):
            return camera_reader(clock)()
    camera = Camera()
    with patch('cartpole_sdk.rig.client.time', clock), patch.object(experiments, 'time', clock), patch.object(manual_capture, 'time', clock):
        yield manual_capture, rig, clock, camera


def stopped_only(rig):
    assert not rig.state.enabled
    assert rig.commands[0][1] == rig.commands[-1][1] == 'STOP'
    assert not any(c[1] in ('ARM', 'MODE', 'HOME', 'REHOME', 'CALIBRATE', 'SET', 'CLEAR', 'A') for c in rig.commands)


def replies(*values):
    answers = iter(values)
    return lambda _: next(answers)


def all_measured(text):
    if 'actual independently measured' in text:
        return '12.5'
    if 'reference method' in text:
        return 'independent inclinometer zeroed to plumb vertical'
    if 'upright basis' in text:
        return 'true-vertical'
    if 'release' in text:
        return 'released'
    return 'ready'


def test_angle_holds_cover_both_directions_and_never_invent_actual_angles():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='angle-map', prompt=all_measured, emit=lambda _: None)
    assert result['completed'] is True and result['early_finish'] is False
    assert result['planned_count'] == result['captured_count'] == 32
    assert result['qualified_count'] == 32
    assert result['hardware_accepted'] is False
    poses = result['poses']
    assert {p['requested_angle_deg'] for p in poses} == {0, -45, 45, -90, 90, -135, 135, 180}
    assert {p['approach'] for p in poses} == {'increasing', 'decreasing'}
    assert {p['repeat'] for p in poses} == {1, 2}
    assert all(p['actual_angle_deg'] == 12.5 for p in poses)
    assert all(p['reference_method'].startswith('independent inclinometer') for p in poses)
    assert all(p['window']['duration_s'] >= 2 for p in poses)
    assert all(p['window']['encoder']['theta_rad']['mean'] == pytest.approx(math.pi) for p in poses)
    assert all(p['camera_snapshot']['vision']['image_angle_rad'] == .04 for p in poses)
    assert not result['firmware_calibration_produced']
    assert len([r for r in rig.records if r['type'] == 'manual_capture_pose']) == 32
    json.dumps(result, allow_nan=False)
    stopped_only(rig)


def test_invalid_actual_input_reprompts_and_unknown_retains_unqualified_data():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='angle-map', emit=lambda _: None,
            prompt=replies('ready', '', 'nan', '45 degrees', 'unknown', 'done'))
    assert result['captured_count'] == 1 and result['qualified_count'] == 0
    assert result['poses'][0]['actual_angle_deg'] is None
    assert result['poses'][0]['reference_method'] is None
    assert result['early_finish'] is True and result['completed'] is False
    assert result['finish_reason'] == 'operator_done'
    assert len([e for e in result['events'] if e['event'] == 'input_rejected']) == 3
    stopped_only(rig)


def test_numeric_actual_requires_independent_reference_method():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='angle-map', emit=lambda _: None,
            prompt=replies('ready', '3.25', '', 'unknown', 'protractor with plumb line', 'done'))
    assert result['poses'][0]['actual_angle_deg'] == 3.25
    assert result['poses'][0]['reference_method'] == 'protractor with plumb line'
    assert result['poses'][0]['qualified'] is True
    stopped_only(rig)


def test_unstationary_hold_is_preserved_and_not_qualified():
    with session() as (manual, rig, clock, camera):
        wait = rig.wait_state
        def moving(*args, **kwargs):
            state = wait(*args, **kwargs)
            rig._state = replace(state, theta=math.pi + .1*math.sin(clock.monotonic()*8), omega=.8)
            return rig.state
        rig.wait_state = moving
        result = manual.run_manual(rig, camera=camera, kind='angle-map', emit=lambda _: None,
            prompt=replies('ready', '0', 'plumb line', 'done'))
    assert result['captured_count'] == 1 and result['qualified_count'] == 0
    assert result['poses'][0]['window']['encoder']['stationary'] is False
    assert result['poses'][0]['window']['encoder']['theta_rad']['span'] > .1
    stopped_only(rig)


def test_friction_releases_are_repeated_disabled_and_keep_working_upright_uncertainty():
    with session() as (manual, rig, clock, camera):
        def respond(text):
            if 'upright basis' in text:
                return 'working-upright'
            return all_measured(text)
        wait = rig.wait_state
        def moving(*args, **kwargs):
            state = wait(*args, **kwargs)
            rig._state = replace(state, theta=.2*math.sin(clock.monotonic()))
            return rig.state
        rig.wait_state = moving
        result = manual.run_manual(rig, camera=camera, kind='capture-friction', prompt=respond, emit=lambda _: None)
    assert result['completed'] and result['captured_count'] == 12
    assert {p['requested_offset_from_upright_deg'] for p in result['releases']} == {-20, -10, -5, 5, 10, 20}
    assert all(p['release_window']['duration_s'] >= 6 for p in result['releases'])
    assert result['upright_basis'] == 'working-upright'
    assert result['true_vertical_qualified'] is False
    assert result['physical_cart_stationarity_certified'] is False
    assert 'step count' in result['physical_cart_restraint']
    stopped_only(rig)


def test_cart_map_retains_measured_anchor_geometry_and_requires_physical_home():
    with session() as (manual, rig, clock, camera):
        values = iter([-101.5, .2, 99.7, -101.4, .3, 99.8])
        current = [0.]
        read = camera.latest
        def camera_at_anchor():
            row = read()
            row['vision']['pivot_px'][0] += current[0]*2
            row['vision']['bob_px'][0] += current[0]*2
            return row
        camera.latest = camera_at_anchor
        def respond(text):
            if 'actual independently measured' in text:
                current[0] = next(values)
                rig._state = replace(rig.state, x=current[0]/1000)
                return str(current[0])
            if 'reference method' in text:
                return 'steel ruler from measured rail midpoint'
            return 'ready'
        result = manual.run_manual(rig, camera=camera, kind='cart-map', prompt=respond, emit=lambda _: None)
    assert result['completed'] and result['captured_count'] == 6
    assert result['qualified_count'] == 6
    assert result['requires_physical_home'] is True
    assert result['step_home_valid_after_manual_move'] is False
    assert 'full HOME' in result['finish_instruction']
    assert {p['requested_position_mm'] for p in result['poses']} == {-100, 0, 100}
    assert result['poses'][0]['actual_position_mm'] == -101.5
    assert result['poses'][0]['window']['camera']['pivot_x_px']['mean'] == pytest.approx(-103.)
    assert result['poses'][1]['window']['camera']['pivot_x_px']['mean'] == pytest.approx(100.4)
    assert all(p['qualified'] for p in result['poses'])
    stopped_only(rig)


@pytest.mark.parametrize('kind', ('angle-map', 'capture-friction', 'cart-map'))
def test_done_before_any_capture_is_explicit_early_finish(kind):
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind=kind, prompt=lambda _: 'done', emit=lambda _: None)
    assert result['captured_count'] == result['qualified_count'] == 0
    assert result['early_finish'] and not result['completed'] and not result['qualified']
    stopped_only(rig)


def test_abort_records_reason_and_stops():
    with session() as (manual, rig, clock, camera):
        with pytest.raises(ValidationError, match='abort'):
            manual.run_manual(rig, camera=camera, kind='angle-map', prompt=lambda _: 'abort', emit=lambda _: None)
    assert any(r['type'] == 'manual_capture_failure' for r in rig.records)
    stopped_only(rig)


@pytest.mark.parametrize('failure', ('timeout', 'health', 'enabled', 'switch', 'cart', 'camera', 'reference', 'home'))
def test_stalled_operator_never_blocks_health_camera_or_deadline(failure):
    release = threading.Event()
    with session() as (manual, rig, clock, camera):
        wait = rig.wait_state
        def waiting(*args, **kwargs):
            state = wait(*args, **kwargs)
            if clock.monotonic() >= .06:
                if failure == 'health': rig._state = replace(state, flags=state.flags & ~1)
                if failure == 'enabled': rig._state = replace(state, flags=state.flags | 2)
                if failure == 'switch': rig._state = replace(state, flags=state.flags | 16)
                if failure == 'cart': rig._state = replace(state, x=.004)
                if failure == 'reference': rig._info.encoder_upright_raw = 331
                if failure == 'home': rig._info.home_epoch = 15
            return rig.state
        rig.wait_state = waiting
        if failure == 'camera':
            frozen = camera.latest()
            camera.latest = lambda: frozen
        def blocked(_):
            release.wait(2.)
            return 'ready'
        try:
            with pytest.raises(ValidationError):
                manual.run_manual(rig, camera=camera, kind='angle-map', prompt=blocked, timeout_s=.3, emit=lambda _: None)
        finally:
            release.set()
    assert camera.checks > 1
    assert clock.monotonic() <= .31
    stopped_only(rig)


@pytest.mark.parametrize('pin', ({'expected_reference': 331}, {'expected_home': 13}))
def test_preflight_honors_saved_reference_and_home_pins_before_prompt(pin):
    with session() as (manual, rig, clock, camera):
        with pytest.raises(ValidationError, match='expected'):
            manual.run_manual(rig, camera=camera, kind='angle-map', prompt=lambda _: pytest.fail('prompted'), emit=lambda _: None, **pin)
    stopped_only(rig)


def test_finish_does_not_hide_camera_or_latched_logger_failure():
    with session() as (manual, rig, clock, camera):
        def done(_):
            rig._latch(RuntimeError('logger write failed'))
            return 'done'
        with pytest.raises(RuntimeError, match='logger write failed'):
            manual.run_manual(rig, camera=camera, kind='angle-map', prompt=done, emit=lambda _: None)
    stopped_only(rig)


def test_original_failure_survives_final_stop_failure():
    with session() as (manual, rig, clock, camera):
        stop = rig.stop
        count = [0]
        def stop_fails():
            count[0] += 1
            stop()
            if count[0] == 2:
                raise RuntimeError('stop failure')
        rig.stop = stop_fails
        with pytest.raises(ValidationError, match='abort'):
            manual.run_manual(rig, camera=camera, kind='angle-map', prompt=lambda _: 'abort', emit=lambda _: None)
    assert any(r['type'] == 'manual_capture_stop' and not r['confirmed'] for r in rig.records)
    stopped_only(rig)


def test_terminal_partial_line_is_nonblocking_and_eof_is_not_done():
    with session() as (manual, rig, clock, camera):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'do')
        os.close(write_fd)
        with os.fdopen(read_fd, 'r') as source, patch.object(manual.sys, 'stdin', source):
            with pytest.raises(ValidationError, match='deadline|input.*closed'):
                manual.run_manual(rig, camera=camera, kind='angle-map', timeout_s=.2, emit=lambda _: None)
    stopped_only(rig)


def test_cart_map_cannot_qualify_repeated_measurements_of_one_physical_position():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='cart-map', prompt=all_measured, emit=lambda _: None)
    assert result['completed'] and result['qualified_count'] == 6
    assert result['qualified'] is False
    assert result['distinct_measured_positions'] == 1
    stopped_only(rig)


def test_marker_loss_is_preserved_as_unqualified_hold_instead_of_discarded():
    with session() as (manual, rig, clock, camera):
        read = camera.latest
        def missing():
            row = read()
            row['vision'].update(detected=False, pivot_px=None, bob_px=None, image_angle_rad=None, length_px=None)
            return row
        camera.latest = missing
        result = manual.run_manual(rig, camera=camera, kind='angle-map', emit=lambda _: None,
            prompt=replies('ready', '0', 'plumb line', 'done'))
    pose = result['poses'][0]
    assert pose['qualified'] is False
    assert pose['window']['camera']['valid_count'] == 0
    assert pose['camera_snapshot']['vision']['detected'] is False
    stopped_only(rig)


def test_fault_mid_hold_retains_partial_window_before_failure_and_stop():
    with session() as (manual, rig, clock, camera):
        wait = rig.wait_state
        def fails(*args, **kwargs):
            state = wait(*args, **kwargs)
            if clock.monotonic() >= .5:
                raise RuntimeError('transport broke in hold')
            return state
        rig.wait_state = fails
        with pytest.raises(RuntimeError, match='transport broke'):
            manual.run_manual(rig, camera=camera, kind='angle-map', prompt=all_measured, emit=lambda _: None)
    partial = next(r for r in rig.records if r['type'] == 'manual_capture_window')
    assert partial['window']['complete'] is False
    assert partial['window']['duration_qualified'] is False
    assert partial['window']['encoder']['sample_count'] > 1
    assert any(r['type'] == 'manual_capture_label' for r in rig.records)
    stopped_only(rig)


def test_done_after_friction_hold_does_not_count_unreleased_trial():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='capture-friction', emit=lambda _: None,
            prompt=replies('working-upright', 'ready', 'unknown', 'done'))
    assert result['captured_count'] == 0 and len(result['poses']) == 1
    assert result['releases'] == [] and result['early_finish']
    stopped_only(rig)


@pytest.mark.parametrize('field,changed,message', [('encoder_upright_raw', 999, 'reference'), ('home_epoch', 22, 'home')])
def test_reference_changes_abort_during_wait_not_just_session_timeout(field, changed, message):
    with session() as (manual, rig, clock, camera):
        released = threading.Event()
        wait = rig.wait_state
        def changed_info(*args, **kwargs):
            state = wait(*args, **kwargs)
            if clock.monotonic() >= .1:
                setattr(rig._info, field, changed)
            return state
        rig.wait_state = changed_info
        try:
            with pytest.raises(ValidationError, match=message):
                manual.run_manual(rig, camera=camera, kind='angle-map', timeout_s=2.,
                    prompt=lambda _: released.wait(2.), emit=lambda _: None)
        finally:
            released.set()
    initial = next(r for r in rig.records if r['type'] == 'manual_capture_start')
    assert initial['info']['encoder_upright_raw'] == 330
    assert initial['info']['home_epoch'] == 14
    stopped_only(rig)


def test_camera_movement_disqualifies_cart_anchor_but_retains_pixel_statistics():
    with session() as (manual, rig, clock, camera):
        read = camera.latest
        def moving_camera():
            row = read()
            displacement = 10*math.sin(clock.monotonic()*4)
            row['vision']['pivot_px'][0] += displacement
            row['vision']['bob_px'][0] += displacement
            return row
        camera.latest = moving_camera
        result = manual.run_manual(rig, camera=camera, kind='cart-map', emit=lambda _: None,
            prompt=replies('ready', '-99.1', 'steel ruler', 'done'))
    pose = result['poses'][0]
    assert pose['window']['camera']['pivot_x_px']['span'] > 10
    assert pose['window']['camera']['pivot_stationary'] is False
    assert pose['qualified'] is False
    stopped_only(rig)


def test_terminal_done_requires_a_complete_line_and_is_not_lost_between_prompts():
    with session() as (manual, rig, clock, camera):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'ready\nunknown\ndone\n')
        os.close(write_fd)
        with os.fdopen(read_fd, 'r') as source, patch.object(manual.sys, 'stdin', source):
            result = manual.run_manual(rig, camera=camera, kind='angle-map', emit=lambda _: None)
    assert result['captured_count'] == 1 and result['early_finish']
    stopped_only(rig)


def test_true_vertical_reference_is_explicit_and_not_inferred_from_working_upright():
    with session() as (manual, rig, clock, camera):
        result = manual.run_manual(rig, camera=camera, kind='capture-friction', emit=lambda _: None,
            prompt=replies('true-vertical', 'plumb line at measured pivot', 'ready', '185.1', 'independent inclinometer', 'released', 'done'))
    release = result['releases'][0]
    assert result['true_vertical_qualified'] is True
    assert result['upright_reference_method'] == 'plumb line at measured pivot'
    assert release['actual_angle_deg'] == 185.1
    assert release['requested_offset_from_upright_deg'] == 5
    assert release['qualified'] is True
    assert release['physical_release_time_verified'] is False
    stopped_only(rig)


def test_friction_release_brackets_operator_delay_in_continuous_raw_logs():
    with session() as (manual, rig, clock, camera):
        holds = [0]
        def respond(text):
            if 'Manually hold' in text:
                holds[0] += 1
                return 'ready' if holds[0] == 1 else 'done'
            if 'Let go' in text:
                for _ in range(40):
                    rig.wait_state(after_tick=rig.state.unwrapped_tick)
                return 'released'
            return all_measured(text)
        result = manual.run_manual(rig, camera=camera, kind='capture-friction', prompt=respond, emit=lambda _: None)
    release = result['releases'][0]
    bracket = release['release_bracket']
    assert bracket['hold_end_host_ns'] == release['window']['host_window_ns'][1]
    assert bracket['acknowledged_host_ns'] - bracket['hold_end_host_ns'] >= 400_000_000
    assert bracket['acknowledged_board_us'] - bracket['hold_end_board_us'] >= 400_000
    assert bracket['physical_release_time_verified'] is False
    assert bracket['requires_continuous_raw_evidence'] is True
    assert release['release_window_origin'] == 'operator_acknowledgement_not_physical_release'
    assert release['release_window']['host_window_ns'][0] >= bracket['acknowledged_host_ns']
    event = next(r for r in rig.records if r['type'] == 'manual_capture_release')
    assert event['release_bracket'] == bracket
    stopped_only(rig)
