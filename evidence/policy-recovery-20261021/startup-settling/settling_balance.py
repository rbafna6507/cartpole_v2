"""Evidence-only startup settling comparison; no training or automatic recovery.

Default settle_ms=0 delegates to the existing immediate balance runner. Explicit
200 sends bounded zero requests through the SAME 20ms lease runner, then requires
its normal start guard before invoking the unchanged actor. Settling is an
unconfirmed diagnostic hypothesis, not an established fix or hardware approval.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from cartpole_sdk.contracts import Acceleration, ValidationError, select_channels
from cartpole_sdk.learning.balance_hardware import (
    BalanceOnlyPolicy, START_LIMITS, _load_policy, _validate_options, run_balance_policy,
)
from cartpole_sdk.rig.neural_runner import run_neural_policy


class SettlingBalancePolicy(BalanceOnlyPolicy):
    """Guarded zero phase followed by the same actor; no weight/state refitting."""

    def __init__(self, actor, *, health_guard, recorder, **kwargs):
        super().__init__(actor, **kwargs)
        if self.observation_contract['angle_source'] != 'filtered':
            raise ValidationError('startup settling research requires the filtered candidate')
        self._health_guard = health_guard
        self._recorder = recorder
        self.settle_ns = 200_000_000
        self._prearm_validated = False
        self._settle_origin = None
        self._settle_previous = None
        self._settled = False
        self._zero_commands = self._feedback_commands = 0
        self.mode = 'settling'

    def reset(self, session):
        super().reset(session)
        self._prearm_validated = False
        self._settle_origin = None
        self._settle_previous = None
        self._settled = False
        self._zero_commands = self._feedback_commands = 0
        self.mode = 'settling'

    def validate_start(self, observation):
        self._health_guard()
        super().validate_start(observation)
        self._prearm_validated = True

    def timing_diagnostics(self):
        return dict(settle_ms=200, phase=self.mode, zero_commands=self._zero_commands,
                    feedback_commands=self._feedback_commands,
                    settling_start_board_ns=self._settle_origin,
                    settling_deadline_board_ns=None if self._settle_origin is None
                    else self._settle_origin+self.settle_ns,
                    semantics='Fixed board-time phase; ordinary host duration/20ms leases still apply.')

    def _record_command(self, observation, intent):
        if intent is not None:
            self._recorder('startup_settling_command', phase=self.mode,
                observation_sequence=observation.sequence, board_ns=observation.available_ns,
                raw_acceleration_m_s2=intent.acceleration_m_s2,
                actor_content_sha256=self.actor['content_sha256'])
        return intent

    def act(self, observation):
        if self.fault_reason is not None:
            return None
        try:
            self._health_guard()
            if self._settled:
                intent = super().act(observation)
                if intent is not None:
                    self._feedback_commands += 1
                return self._record_command(observation, intent)
            # run_policy calls validate_start before ARM. Shadow mode reaches
            # this branch while stopped and must pass that same guard too.
            if not self._prearm_validated:
                self.validate_start(observation)
            x, velocity, theta, omega, _, brake = self._values(observation)
            raw_and_selected = select_channels(observation,
                (self._raw_angle_channel,)+self.channels,
                now_ns=observation.available_ns, max_age_ns=20_000_000)
            if (max(s.effective_ns for s in raw_and_selected)
                    - min(s.effective_ns for s in raw_and_selected) > 10_000_000):
                raise ValidationError('startup settling raw/selected timestamp skew exceeds one period')
            raw_theta = raw_and_selected[0].value
            if (abs(x) > START_LIMITS['position_m']
                    or abs(velocity) > START_LIMITS['velocity_m_s'] or brake != 0
                    or abs(raw_theta) > math.radians(10.) or abs(omega) > 3.):
                raise ValidationError('startup settling envelope lost: require START cart/speed/brake bounds, '
                                      '|raw angle|<=10deg and |rate|<=3rad/s')
            now = observation.available_ns
            if self._settle_previous is not None:
                sequence, previous_ns = self._settle_previous
                if observation.sequence <= sequence or abs(now-previous_ns-10_000_000) > 5_000_000:
                    raise ValidationError('startup settling replayed observation or incompatible 100Hz cadence')
            if self._settle_origin is None:
                self._settle_origin = now
                self._recorder('startup_settling_start', board_ns=now,
                    first_observation_sequence=observation.sequence,
                    deadline_board_ns=now+self.settle_ns, settle_ms=200,
                    time_basis='First post-ARM policy observation, after normal pre-ARM full start guard; '
                               'in stopped shadow this is the first shadow observation.',
                    raw_angle_rad=raw_theta, filtered_angle_rad=theta,
                    angular_rate_rad_s=omega, position_m=x, commanded_velocity_m_s=velocity)
            elapsed = now-self._settle_origin
            if elapsed >= self.settle_ns:
                # No retry/extension if this stricter guard fails at the first
                # eligible frame. Do not reset session, limits, reference,
                # fault latch, actor weights, or numeric backend.
                super().validate_start(observation)
                self._previous = None  # Only actor cadence history is reset.
                self._settled = True
                self.mode = 'feedback'
                self._recorder('startup_settling_transfer', board_ns=now,
                    observation_sequence=observation.sequence, elapsed_ns=elapsed,
                    full_start_guard_pass=True, zero_commands=self._zero_commands,
                    raw_angle_rad=raw_theta, filtered_angle_rad=theta,
                    angular_rate_rad_s=omega, position_m=x, commanded_velocity_m_s=velocity,
                    actor_content_sha256=self.actor['content_sha256'])
                intent = super().act(observation)
                if intent is not None:
                    self._feedback_commands += 1
                return self._record_command(observation, intent)
            self._settle_previous = observation.sequence, now
            self._zero_commands += 1
            return self._record_command(observation, Acceleration(0.))
        except ValidationError as error:
            self.fault_reason = str(error)
            self._recorder('startup_settling_refused', phase=self.mode,
                observation_sequence=observation.sequence, board_ns=observation.available_ns,
                reason=self.fault_reason, zero_commands=self._zero_commands)
            return None


def run_settling_balance_policy(rig, actor_path, *, expected_upright_raw,
        development_only=False, execute=False, duration_s=1., max_acceleration=.25,
        preflight_s=2., guard_profile='commissioning', inference_backend='numpy',
        expected_actor_sha256=None, settle_ms=0):
    """Same immediate runner by default; explicit200 is a research intervention.

    Total ARM duration includes settling. It is never extended for settling or
    a failed handoff. A200ms phase requires >=250ms total duration to leave an
    ordinary feedback opportunity within the runner's existing stop reserve.
    """
    options = dict(expected_upright_raw=expected_upright_raw,
        development_only=development_only, execute=execute, duration_s=duration_s,
        max_acceleration=max_acceleration, preflight_s=preflight_s,
        guard_profile=guard_profile, inference_backend=inference_backend,
        expected_actor_sha256=expected_actor_sha256)
    if type(settle_ms) is int and settle_ms == 0:
        return run_balance_policy(rig, actor_path, **options)
    try:
        _validate_options(**{k:v for k,v in options.items()
                             if k not in ('inference_backend','expected_actor_sha256')})
        if type(settle_ms) is not int or settle_ms != 200:
            raise ValidationError('settle_ms must be explicit integer0 or200')
        if duration_s < .25:
            raise ValidationError('200ms settling requires at least0.25s total duration; duration includes settling')
        def health_guard():
            rig._require()
            state = rig.state
            rig._fresh(state)
            if not state.healthy or not state.homed or not state.switch_profile:
                raise ValidationError('startup settling requires fresh healthy homed switch-profile telemetry')
        def reference_guard():
            actual = rig._info
            if (actual is None or actual.encoder_upright_raw != expected_upright_raw
                    or actual.reference_saved is not True or actual.encoder_conf_valid is not True):
                raise ValidationError('balance-only current saved upright reference differs or is invalid')
        # Preserve normal bounded JSON/hash validation and inference warmup.
        base = _load_policy(actor_path, reference_guard=reference_guard,
            guard_profile=guard_profile, max_acceleration=max_acceleration if execute else None,
            inference_backend=inference_backend)
        if expected_actor_sha256 is not None and base.actor['content_sha256'] != expected_actor_sha256:
            raise ValidationError('selected actor file changed; reload the explicitly selected actor')
        policy = SettlingBalancePolicy(base.actor, channels=base.channels,
            reference_guard=reference_guard, guard_profile=guard_profile,
            max_acceleration=max_acceleration if execute else None,
            inference_backend=inference_backend, health_guard=health_guard, recorder=rig._record)
        rig._stopped_healthy()
        info = rig.get_info()
        if info.encoder_upright_raw != expected_upright_raw:
            raise ValidationError('balance-only saved upright reference differs from expected count')
        rig._record('startup_settling_boundary', settle_ms=200, total_duration_s=duration_s,
            duration_includes_settling=True, no_handoff_wait_extension=True,
            start_limits=START_LIMITS, settling_raw_angle_limit_rad=math.radians(10.),
            settling_rate_limit_rad_s=3., guard_profile=guard_profile,
            actor_content_sha256=policy.actor['content_sha256'], expected_upright_raw=expected_upright_raw,
            inference_backend=policy.inference_provenance,
            harness_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            status='DEVELOPMENT_ONLY', hardware_accepted=False,
            hypothesis='Startup settling is an unconfirmed diagnostic intervention, not an established fix.')
        result = run_neural_policy(rig, policy, development_only=True, execute=execute,
            duration_s=duration_s, max_acceleration=max_acceleration, preflight_s=preflight_s)
        return dict(result, task='balance-startup-settling-research', settle_ms=200,
            duration_s=duration_s, expected_upright_raw=expected_upright_raw,
            guard_profile=guard_profile, run_limits=policy.run_limits,
            actor_content_sha256=policy.actor['content_sha256'],
            settling=policy.timing_diagnostics(), hardware_accepted=False)
    finally:
        rig.stop()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor',required=True,type=Path)
    parser.add_argument('--expected-actor-sha256',required=True)
    parser.add_argument('--port',required=True)
    parser.add_argument('--expected-upright-raw',required=True,type=int)
    parser.add_argument('--settle-ms',choices=(0,200),default=0,type=int)
    parser.add_argument('--duration',type=float,default=1.,help='Total duration including settling; >=0.25 for200ms.')
    parser.add_argument('--max-acceleration',type=float,default=.25)
    parser.add_argument('--guard-profile',choices=('commissioning','rig'),default='commissioning')
    parser.add_argument('--preflight-seconds',type=float,default=2.)
    parser.add_argument('--inference-backend',choices=('numpy','python'),default='numpy')
    parser.add_argument('--development-only',action='store_true')
    parser.add_argument('--execute',action='store_true',help='Omit for stopped shadow only.')
    parser.add_argument('--log-dir',required=True,type=Path)
    args=parser.parse_args(argv)
    # Import device support only for an explicitly invoked CLI; importing this
    # module and all tests cannot open hardware.
    from cartpole_sdk.rig import Rig
    from cartpole_sdk.rig.runtime import defer_cyclic_gc
    with defer_cyclic_gc(), Rig(args.port,rate_hz=100,log_dir=args.log_dir) as rig:
        result=run_settling_balance_policy(rig,args.actor,
            expected_upright_raw=args.expected_upright_raw,expected_actor_sha256=args.expected_actor_sha256,
            development_only=args.development_only,execute=args.execute,duration_s=args.duration,
            max_acceleration=args.max_acceleration,preflight_s=args.preflight_seconds,
            guard_profile=args.guard_profile,inference_backend=args.inference_backend,settle_ms=args.settle_ms)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
