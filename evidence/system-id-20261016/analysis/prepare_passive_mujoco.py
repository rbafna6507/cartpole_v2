"""Prepare an offline-only MuJoCo candidate and verify the parameter mapping.

This is a mathematical implementation check, not held-out physical validation.
No hardware, live calibration, package defaults or gain profiles are changed.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import mujoco
import cartpole_sdk.sim.backend as backend_module
import cartpole_sdk.sim.config as config_module
import cartpole_sdk.sim.model as model_module
from cartpole_sdk.sim.backend import MujocoBackend
from cartpole_sdk.sim.config import SimulationConfig


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def advance(theta, omega, h, gravity, damping):
    def rhs(q, w):
        return w, gravity * math.sin(q) - damping * w
    k1 = rhs(theta, omega)
    k2 = rhs(theta + h*k1[0]/2, omega + h*k1[1]/2)
    k3 = rhs(theta + h*k2[0]/2, omega + h*k2[1]/2)
    k4 = rhs(theta + h*k3[0], omega + h*k3[1])
    return (theta + h*(k1[0]+2*k2[0]+2*k3[0]+k4[0])/6,
            omega + h*(k1[1]+2*k2[1]+2*k3[1]+k4[1])/6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-summary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.training_summary.read_text())
    fit = report['magnetic_reports']['viscous']
    assert report['status'] == 'training_only_no_model_promotion'
    assert not report['heldout_read'] and fit['training_checks_pass']
    assert not fit['statistical_checks_pass'] and fit['recommended_model'] is None
    assert not report['magnetic_reports']['viscous_coulomb']['training_checks_pass']
    parameters = fit['parameters']
    length = parameters['effective_length_m']
    damping = parameters['angular_damping_per_s']
    assert parameters['coulomb_rad_per_s2'] == 0 and length > 0 and damping >= 0
    defaults = SimulationConfig()
    inertia = .75 * defaults.pole_mass_kg * length**2
    overrides = dict(effective_length_m=length, hinge_damping=damping*inertia)
    config = SimulationConfig(**overrides)
    # MuJoCo's 1 ms Euler implementation must match the mapped equation locally,
    # with no force saturation. These are numerical checks, not physical gates.
    trials = []
    for excursion in (-1.1, -.3, .3, 1.1):
        for initial_omega in (-1.3, 0., 1.3):
            theta = math.pi + excursion
            omega = initial_omega
            sim = MujocoBackend(config)
            sim.reset(state=(0., 0., theta, omega))
            expected_acceleration = 9.81/length*math.sin(theta)-damping*omega
            max_angle_error = max_cart_acceleration = max_force = 0.
            first_acceleration_error = None
            saturated = False
            for step in range(500):
                sim.step(None)  # zero cart acceleration intent; retains cart hold
                if step == 0:
                    first_acceleration_error = abs(float(sim.data.qacc[sim._pole])-expected_acceleration)
                for _ in range(4):
                    theta, omega = advance(theta, omega, .00025, 9.81/length, damping)
                error = math.atan2(math.sin(sim.ground_truth.theta-theta), math.cos(sim.ground_truth.theta-theta))
                max_angle_error = max(max_angle_error, abs(error))
                max_cart_acceleration = max(max_cart_acceleration, abs(sim.diagnostics.achieved_acceleration_m_s2))
                max_force = max(max_force, abs(sim.diagnostics.applied_force_n))
                saturated |= sim.diagnostics.force_saturated
            trials.append(dict(excursion_rad=excursion, initial_omega_rad_s=initial_omega,
                first_acceleration_error_rad_s2=first_acceleration_error,
                maximum_angle_difference_rad=max_angle_error,
                maximum_cart_acceleration_m_s2=max_cart_acceleration,
                maximum_applied_force_n=max_force, force_saturated=saturated))
            sim.close()
    checks = dict(
        instantaneous_equation=all(x['first_acceleration_error_rad_s2'] < 1e-9 for x in trials),
        half_second_trajectory=all(x['maximum_angle_difference_rad'] < .01 for x in trials),
        fixed_cart=all(x['maximum_cart_acceleration_m_s2'] < 1e-9 for x in trials),
        unsaturated=all(not x['force_saturated'] for x in trials))
    assert all(checks.values()), checks
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'model-config.json').write_text(json.dumps(overrides, indent=2)+'\n')
    provenance = dict(status='offline training candidate; independent physical validation pending',
        accepted_physical_model=False, recommended_for_hardware_rl=False,
        source_summary_sha256=sha(args.training_summary), script_sha256=sha(Path(__file__)),
        mujoco_version=mujoco.__version__,
        simulator_sources={module.__name__: sha(Path(module.__file__))
                           for module in (backend_module, config_module, model_module)},
        full_simulation_config=asdict(config), inferred_parameters=parameters,
        hinge_mapping='hinge_damping = gamma * I_pivot; I_pivot = 0.75 * assumed_pole_mass * L_eff**2',
        pivot_inertia_kg_m2=inertia,
        local_measurement_comparison='physical_theta = raw_encoder_theta - training_angle_offset; offline down-region assumption only',
        exclusions=['No sensor-bias or live encoder calibration change.',
                    'Masses, force authority, cart damping and actuator behavior remain assumed.',
                    'The displayed uniform-rod length is 1.5*L_eff, not measured physical pole length.',
                    'No Coulomb/stiction component; the primary viscous+Coulomb fit was rejected.',
                    'Camera geometry coverage failed for the second training episode.',
                    'No inference of full-swing, upright or driven-cart validity from passive training.'])
    (args.output/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    verification = dict(purpose='numerical mapping check only; no physical validation',
        thresholds=dict(acceleration_rad_s2=1e-9, angle_rad=.01, cart_acceleration_m_s2=1e-9),
        horizon_s=.5, mujoco_step_s=.001, reference_rk4_step_s=.00025, checks=checks, trials=trials)
    (args.output/'mapping-verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    print(json.dumps(dict(output=str(args.output), checks=checks,
        maximum_angle_difference_rad=max(x['maximum_angle_difference_rad'] for x in trials))))


if __name__ == '__main__':
    main()
