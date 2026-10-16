"""Float64 feasibility forecasts checked against the actual native headers.

The compiler is a test dependency only; production forecasting is pure Python.
"""
from dataclasses import asdict, replace
import importlib
import math
from pathlib import Path
import random
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from cartpole_sdk.control.motion import _Float32
from cartpole_sdk.control.parameters import Gains, gains, load_tuned_parameters


ROOT = Path(__file__).resolve().parents[1]
PARAMETER_NAMES = (
    'leff', 'vmax', 'vmax_b', 'catch_a', 'catch_r', 'catch_v', 'catch_da',
    'amax_b', 'amax_s', 'jmax', 'rail', 'rail_margin', 'rail_hysteresis', 'giveup',
)


def fast(*args, **kwargs):
    # Missing implementation is an assertion failure, not a collection error.
    try:
        module = importlib.import_module('cartpole_sdk.control.forecast')
    except ModuleNotFoundError:
        pytest.fail('the pure-Python capture forecast is not implemented')
    return module.can_capture_fast(*args, **kwargs)


@pytest.fixture(scope='module')
def native_capture(tmp_path_factory):
    """Compile the live header unchanged, without Python motion/reference code."""
    build = tmp_path_factory.mktemp('capture-oracle')
    source = build / 'capture.cpp'
    executable = build / 'capture'
    reads = ''.join(f' >> p.{name}' for name in PARAMETER_NAMES)
    source.write_text(r'''
#include <iostream>
#include "swing_controller.h"
int main() {
  swing_control::Parameters p;
  swing_control::Gains k;
  float theta, omega, x, v, acceleration;
  while (std::cin''' + reads + r''' >> k.k1 >> k.k2 >> k.k3 >> k.k4
      >> theta >> omega >> x >> v >> acceleration) {
    bool accepted = swing_control::canCapture(p,k,theta,omega,x,v,acceleration);
    // Report the first native braking latch independently for rail fixtures.
    cart_motion::State motion;
    motion.velocity=v; motion.acceleration=acceleration;
    float q=theta, w=omega, xx=x;
    int brake_tick=-1;
    for(int tick=0;tick<36;++tick) {
      float request=swing_control::balance(k,q,w,xx,motion.velocity);
      motion=cart_motion::advance(motion,xx,request,swing_control::speedLimit(p,true),
        p.amax_b,fmaxf(p.amax_s,p.amax_b),p.jmax,p.rail,.005f,p.rail_margin);
      if(motion.brake_direction) { brake_tick=tick; break; }
      xx+=motion.velocity*.005f;
      float alpha=(swing_control::kGravity*sinf(q)-motion.acceleration*cosf(q))/p.leff;
      q=swing_control::wrap(q+w*.005f+.5f*alpha*.005f*.005f);
      w+=alpha*.005f;
    }
    std::cout << accepted << " " << brake_tick << '\n';
  }
}
''')
    compiler = shutil.which('c++') or '/usr/bin/c++'
    subprocess.run([
        compiler, '-std=c++17', '-O2', '-fno-fast-math',
        '-I', str(ROOT / 'firmware/teensy_executor'), str(source),
        '-o', str(executable),
    ], check=True, capture_output=True, text=True, timeout=60)

    def run(cases):
        rows = []
        for p, k, state in cases:
            values = [getattr(p, name) for name in PARAMETER_NAMES]
            values.extend((k.k1, k.k2, k.k3, k.k4, *state))
            rows.append(' '.join(format(value, '.17g') for value in values))
        result = subprocess.run([str(executable)], input='\n'.join(rows)+'\n',
                                capture_output=True, text=True, check=True, timeout=30)
        outputs = [(bool(int(row[0])), int(row[1]))
                   for row in (line.split() for line in result.stdout.splitlines())]
        assert len(outputs) == len(cases)
        return outputs

    return run


def test_accepts_stationary_upright_without_mutation(native_capture):
    p = load_tuned_parameters()
    k = gains(p)
    before = asdict(p), asdict(k)
    assert native_capture([(p, k, (0, 0, 0, 0, 0))])[0][0] is True
    assert fast(p, k, 0, 0, 0, 0) is True
    assert (asdict(p), asdict(k)) == before


@pytest.mark.parametrize('state', [
    (.1, -1., 0., 0., 0.), (-.1, 1., 0., 0., 0.),
    (.05, 0., .02, -.1, 0.), (-.05, 0., -.02, .1, 0.),
    (.15, -1.5, .03, .1, 1.5), (-.15, 1.5, -.03, -.1, -1.5),
])
def test_representative_captures_match_native(native_capture, state):
    p = load_tuned_parameters()
    k = gains(p)
    expected = native_capture([(p, k, state)])[0][0]
    assert expected is True
    assert fast(p, k, *state) is expected


@pytest.mark.parametrize('state', [
    (.6, 0., 0., 0., 0.), (0., 3., 0., 0., 0.),
    (0., 0., .12, 0., 0.), (0., 0., 0., .3, 0.),
    (0., 0., 0., 0., 4.01),
])
def test_precheck_limits_reject_capture(native_capture, state):
    p = load_tuned_parameters()
    k = gains(p)
    assert native_capture([(p, k, state)])[0][0] is False
    assert fast(p, k, *state) is False


def test_demand_limit_and_outbound_angle_guard(native_capture):
    p = load_tuned_parameters()
    cases = [
        (p, Gains(-1000, 0, 0, 0), (.05, 0, 0, 0, 50)),
        # The balance forecast converges if the outbound-angle guard is removed.
        (p, gains(p), (.21, .1, 0, 0, 4.592581577981651)),
    ]
    assert all(not accepted for accepted, _ in native_capture(cases))
    assert all(not fast(p, k, *state) for p, k, state in cases)


def test_current_acceleration_can_change_capture_feasibility(native_capture):
    p = load_tuned_parameters()
    k = gains(p)
    cases = [(p, k, (.1, -1., 0, 0, a)) for a in (0., 4.1)]
    assert [accepted for accepted, _ in native_capture(cases)] == [True, False]
    assert [fast(p, k, *state) for p, k, state in cases] == [True, False]


def test_forecast_rejects_rail_braking_after_initial_guards(native_capture):
    p = replace(load_tuned_parameters(), rail=.08)
    k = Gains(0, 0, 0, 0)
    cases = [(p, k, (0, 0, sign*.04, sign*.25, 0)) for sign in (-1, 1)]
    outputs = native_capture(cases)
    assert all(not accepted and 0 <= brake_tick < 36 for accepted, brake_tick in outputs)
    assert all(not fast(p, k, *state) for p, k, state in cases)
    # Moving inward from the same initial cart location is feasible.
    assert fast(p, k, 0, 0, .04, -.1, 0) is True


def test_forecast_rejects_divergence_and_giveup(native_capture):
    p = load_tuned_parameters()
    k = Gains(0, 0, 0, 0)
    cases = [(p, k, (.05, 0, 0, 0, 0)),
             (replace(p, giveup=.06), k, (.05, 0, 0, 0, 0))]
    assert all(not accepted for accepted, _ in native_capture(cases))
    assert all(not fast(p, k, *state) for p, k, state in cases)


def test_geometry_and_mode_speed_limits(native_capture):
    p = replace(load_tuned_parameters(), rail=.1, rail_margin=.03, vmax_b=.1)
    k = Gains(0, 0, 0, 0)
    cases = [(p, k, (0, 0, x, v, 0)) for x, v in ((.035, 0), (.045, 0), (0, .1))]
    assert [accepted for accepted, _ in native_capture(cases)] == [True, False, False]
    assert [fast(p, k, *state) for p, k, state in cases] == [True, False, False]


@pytest.mark.parametrize('index', range(5))
@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_nonfinite_state_fails_closed(index, value):
    p = load_tuned_parameters()
    state = [0., 0., 0., 0., 0.]
    state[index] = value
    assert fast(p, gains(p), *state) is False


def test_nonfinite_gains_and_parameters_fail_closed():
    p = load_tuned_parameters()
    assert fast(p, Gains(math.nan, 0, 0, 0), 0, 0, 0, 0) is False
    bad_p = SimpleNamespace(**dict(asdict(p), leff=math.nan))
    assert fast(bad_p, gains(p), 0, 0, 0, 0) is False


def test_binary32_motion_inputs_are_not_mutated(native_capture):
    p = load_tuned_parameters()
    k = gains(p)
    state = tuple(map(_Float32, (.1, -1, .02, -.1, .5)))
    before = tuple(state)
    expected = native_capture([(p, k, state)])[0][0]
    assert fast(p, k, *state) is expected
    assert state == before
    assert all(type(value) is _Float32 for value in state)


def test_seeded_feasibility_cases_match_native(native_capture):
    rng = random.Random(20261016)
    cases = []
    for overrides in ({}, {'jmax': 600.}, {'jmax': 30., 'rail': .15}):
        p = replace(load_tuned_parameters(), **overrides)
        k = gains(p)
        for _ in range(250):
            state = (rng.uniform(-.3, .3), rng.uniform(-2.8, 2.8),
                     rng.uniform(-.09, .09), rng.uniform(-.28, .28),
                     rng.uniform(-4., 4.))
            cases.append((p, k, state))
    outputs = native_capture(cases)
    assert sum(accepted for accepted, _ in outputs) > 50
    for (p, k, state), (expected, _) in zip(cases, outputs):
        assert fast(p, k, *state) is expected, (p, state, expected)


def test_speed_switch_boundary_is_conservatively_rejected(native_capture):
    p = replace(load_tuned_parameters(), vmax_b=.35, amax_b=8., rail=.1)
    k = gains(p)
    # The float64 forecast lands exactly on v + a*a/(2*j) == vmax at
    # forecast step 12. Float32 may choose another branch at that boundary.
    state = (.1373024433631766, -.6176467890940165, -.042786526497364745,
             .2525375058275068, 2.167261462231867)
    assert native_capture([(p, k, state)])[0][0] is True
    assert fast(p, k, *state) is False


def test_close_capture_position_boundary_is_conservatively_rejected(native_capture):
    p = load_tuned_parameters()
    k = Gains(0, 0, 0, 0)
    state = (0, 0, .1199995, 0, 0)
    assert native_capture([(p, k, state)])[0][0] is True
    assert fast(p, k, *state) is False


def test_tight_speed_cap_does_not_admit_native_infeasible_cases(native_capture):
    p = replace(load_tuned_parameters(), vmax_b=.35, amax_b=8., rail=.1)
    k = gains(p)
    rng = random.Random(41)
    cases = [(p, k, (rng.uniform(-.3, .3), rng.uniform(-2.8, 2.8),
                     rng.uniform(-.069, .069), rng.uniform(-.28, .28),
                     rng.uniform(-4., 4.))) for _ in range(250)]
    outputs = native_capture(cases)
    actual = [fast(p, k, *state) for p, k, state in cases]
    assert any(actual) and not all(actual)
    for accepted, (native_accepted, _) in zip(actual, outputs):
        assert not accepted or native_accepted
