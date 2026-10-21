"""Bounded, development-only balance rehearsal through the normal SDK runner.

This command needs an already homed, stopped rig and a manually prepared upright
start. It never swings up, recenters, clears faults, writes parameters or changes
calibration. Limits apply to observed state, not independently measured truth;
STOP/lease expiry is not a model of physical stopping distance.
"""
import argparse
from hashlib import sha256
import gc
import json
import math
from pathlib import Path

from cartpole_sdk.contracts import ValidationError, validate_observation
from cartpole_sdk.policies.neural import NeuralPolicy, load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels, select_rig_observation
from cartpole_sdk.rig.neural_runner import run_neural_policy


START_LIMITS = dict(position_m=.015, velocity_m_s=.025, angle_rad=.07, angular_rate_rad_s=.15)
RUN_LIMITS = dict(position_m=.12, velocity_m_s=.25, angle_rad=.15, angular_rate_rad_s=1.)
MAX_DURATION_S = 10.


class BalanceOnlyPolicy(NeuralPolicy):
    """The unchanged numeric actor with start and per-action stop boundaries."""
    def __init__(self, actor, *, channels, reference_guard=None):
        super().__init__(actor, channels=channels)
        self.reference_guard = reference_guard
        if (self.observation_contract['angle_source'] != 'raw' or
                self.observation_contract['angle_frame_id'] != 'encoder-zero'):
            raise ValidationError('balance-only currently requires the raw encoder-zero actor contract')
        if self.executor_parameters is None:
            raise ValidationError('balance-only requires a complete trained executor snapshot')
        self.position_limit = min(RUN_LIMITS['position_m'],
            self.executor_parameters['rail']-self.executor_parameters['rail_margin'])
        if self.position_limit <= START_LIMITS['position_m']:
            raise ValidationError('balance-only start region does not fit the saved rail envelope')
        self._balance_started = False

    def reset(self, session):
        super().reset(session)
        self._balance_started = False

    def _values(self, observation):
        if self.reference_guard is not None:
            self.reference_guard()
        validate_observation(self.session, observation)
        return tuple(sample.value for sample in select_rig_observation(
            observation, self.channels, contract=self.observation_contract))

    def validate_start(self, observation):
        """Called by run_policy before ARM, and again on the first action."""
        x, velocity, theta, omega, _, brake = self._values(observation)
        if (abs(x) > START_LIMITS['position_m'] or abs(velocity) > START_LIMITS['velocity_m_s'] or
                abs(theta) > START_LIMITS['angle_rad'] or abs(omega) > START_LIMITS['angular_rate_rad_s'] or
                brake != 0):
            raise ValidationError('balance-only requires a centered, nearly stationary upright start '
                '(|x|<=.015 m, |commanded v|<=.025 m/s, |angle|<=.07 rad, |rate|<=.15 rad/s, no rail braking)')

    def act(self, observation):
        if self.fault_reason is not None:
            return None
        try:
            if not self._balance_started:
                self.validate_start(observation)
                self._balance_started = True
            x, velocity, theta, omega, _, brake = self._values(observation)
            if (abs(x) >= self.position_limit or abs(velocity) >= RUN_LIMITS['velocity_m_s'] or
                    abs(theta) >= RUN_LIMITS['angle_rad'] or
                    abs(omega) >= RUN_LIMITS['angular_rate_rad_s'] or brake != 0):
                raise ValidationError('balance-only observed angle/rate/cart/commanded-speed envelope lost or rail braking active')
            return super().act(observation)
        except ValidationError as error:
            self.fault_reason = str(error)
            return None


def _load_policy(actor_path, *, reference_guard=None):
    # Use the ordinary bounded JSON/content/runtime-hash loader before adding
    # constraints. No source hashes or acceptance fields are rewritten.
    policy = load_neural_policy(actor_path, channels=rig_channels(angle_source='raw'))
    return BalanceOnlyPolicy(policy.actor, channels=policy.channels, reference_guard=reference_guard)


def _validate_options(*, development_only, execute, expected_upright_raw,
                      duration_s, max_acceleration, preflight_s):
    if development_only is not True or type(execute) is not bool:
        raise ValidationError('balance-only requires explicit development_only=True and boolean execute')
    if type(expected_upright_raw) is not int or not 0 <= expected_upright_raw < 4096:
        raise ValidationError('explicit expected saved upright reference count in 0..4095 required')
    if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or not .001 <= duration_s <= MAX_DURATION_S:
        raise ValidationError('balance-only duration must be within .001..10 seconds')
    if type(max_acceleration) not in (int, float) or not math.isfinite(max_acceleration) or not 0 < max_acceleration <= 25:
        raise ValidationError('balance-only acceleration ceiling must be positive and at most 25 m/s²')
    if type(preflight_s) not in (int, float) or not math.isfinite(preflight_s) or not 0 < preflight_s <= 30:
        raise ValidationError('balance-only sensor preflight must be within 0..30 seconds')


def run_balance_policy(rig, actor_path, *, expected_upright_raw, development_only=False,
                       execute=False, duration_s=1., max_acceleration=.25, preflight_s=2.):
    """Use the validated artifact, existing live admission and 20 ms SDK leases.

    The expected count binds this invocation to an operator-verified saved
    reference. Equality alone does not establish true vertical or sign accuracy.
    All failures stop; no fallback controller or automatic recovery is selected.
    """
    options = dict(development_only=development_only, execute=execute,
        expected_upright_raw=expected_upright_raw, duration_s=duration_s,
        max_acceleration=max_acceleration, preflight_s=preflight_s)
    _validate_options(**options)
    try:
        from cartpole_sdk.rig import runtime
        def reference_guard():
            # The shared preflight refreshes Rig._info. Inspect that latest
            # immutable packet before ARM and every action, without issuing an
            # INFO command on the armed, telemetry-paced control path.
            actual = rig._info
            if (actual is None or actual.encoder_upright_raw != expected_upright_raw or
                    actual.reference_saved is not True or actual.encoder_conf_valid is not True):
                raise ValidationError('balance-only current saved upright reference differs or is invalid')
        policy = _load_policy(actor_path, reference_guard=reference_guard)
        rig._stopped_healthy()
        info = rig.get_info()
        if info.encoder_upright_raw != expected_upright_raw:
            raise ValidationError('balance-only saved upright reference differs from the expected count')
        rig._record('balance_only_boundary', expected_upright_raw=expected_upright_raw,
            start_limits=START_LIMITS, run_limits=dict(RUN_LIMITS, position_m=policy.position_limit),
            max_duration_s=MAX_DURATION_S, actor_sha256=policy.actor['content_sha256'],
            boundary_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            runtime_helper_sha256=sha256(Path(runtime.__file__).read_bytes()).hexdigest(),
            gc_policy=dict(cyclic_gc_enabled=gc.isenabled(),
                           scope='CLI defers cyclic GC from before Rig creation until after STOP/close; direct API callers own their context.'),
            hardware_accepted=False, state_basis='Observed encoder and commanded cart state; no truth or stopping-distance guarantee')
        result = run_neural_policy(rig, policy, development_only=True, execute=execute,
            duration_s=duration_s, max_acceleration=max_acceleration, preflight_s=preflight_s)
        return dict(result, task='balance-only', expected_upright_raw=expected_upright_raw,
                    hardware_accepted=False)
    finally:
        # Also covers reference/actor failures before the shared runner starts.
        rig.stop()


def main(argv=None, *, rig_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', required=True, type=Path, help='Validated numeric actor.json; never a Torch checkpoint.')
    parser.add_argument('--port', required=True, help='Explicit serial device path.')
    parser.add_argument('--expected-upright-raw', required=True, type=int,
                        help='Previously verified saved encoder reference count, 0..4095. Does not calibrate the rig.')
    parser.add_argument('--development-only', action='store_true', help='Acknowledge unqualified development inference.')
    parser.add_argument('--execute', action='store_true', help='Explicitly arm; omitted means stopped shadow only.')
    parser.add_argument('--duration', type=float, default=1., help='Requested duration, .001..10 seconds (default 1).')
    parser.add_argument('--max-acceleration', type=float, default=.25,
                        help='Raw demand ceiling in m/s², at most 25. Excess faults; no clipping (default .25).')
    parser.add_argument('--preflight-seconds', type=float, default=2., help='Stopped sensor acquisition deadline.')
    parser.add_argument('--log-dir', type=Path, help='SDK JSONL trace directory.')
    args = parser.parse_args(argv)
    options = dict(development_only=args.development_only, execute=args.execute,
        expected_upright_raw=args.expected_upright_raw, duration_s=args.duration,
        max_acceleration=args.max_acceleration, preflight_s=args.preflight_seconds)
    try:
        _validate_options(**options)
        _load_policy(args.actor)  # Reject invalid configuration before opening serial.
        from cartpole_sdk.rig import Rig
        from cartpole_sdk.rig.runtime import defer_cyclic_gc
        factory = Rig if rig_factory is None else rig_factory
        with defer_cyclic_gc(), factory(args.port, rate_hz=100, log_dir=args.log_dir) as rig:
            result = run_balance_policy(rig, args.actor, **options)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, ImportError, RuntimeError) as error:
        parser.exit(2, f'cartpole balance-only inference: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
