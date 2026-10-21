"""A selected development balance actor on the console's existing Rig."""
import math
from pathlib import Path
import sys

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_hardware import START_LIMITS, _load_policy, run_balance_policy
from cartpole_sdk.recording import canonical_json
from .neural_runner import validate_live_executor
from .runtime import defer_cyclic_gc


DEFAULT_DURATION_S = 5.
HELP = 'policy load PATH, policy status, policy check, policy shadow [seconds], policy run [seconds], policy unload'


class ConsolePolicy:
    """Selection never grants motion; only the explicit run command can arm."""
    def __init__(self):
        self.path = None
        self.policy = None
        self.reference = None
        self.invalidated = False

    @staticmethod
    def validate_actor(path):
        return _load_policy(path, guard_profile='rig')

    @staticmethod
    def _reference(info):
        if (info.reference_saved is not True or info.encoder_conf_valid is not True or
                type(info.encoder_upright_raw) is not int or not 0 <= info.encoder_upright_raw < 4096):
            raise ValidationError('policy requires a valid, already saved encoder reference; calibrate explicitly before loading')
        return (info.encoder_upright_raw, info.firmware)

    def load(self, rig, path):
        path = Path(path).expanduser().resolve()
        policy = self.validate_actor(path)
        rig._stopped_healthy()
        reference = self._reference(rig.get_info())
        # Commit the selection only after all validation succeeds.
        self.path, self.policy, self.reference = path, policy, reference
        self.invalidated = False

    def _require_selected(self):
        if self.policy is None:
            raise ValidationError('no learned policy selected; use policy load PATH first')

    def _reference_matches(self, info):
        try:
            matches = self._reference(info) == self.reference
        except ValidationError:
            matches = False
        if not matches:
            self.invalidated = True
        return matches and not self.invalidated

    def status(self, rig):
        if self.policy is None:
            return dict(selected=False, task='balance-only', hardware_accepted=False)
        info = rig.get_info()
        return dict(selected=True, task='balance-only', status='DEVELOPMENT_ONLY',
            actor_path=str(self.path), actor_sha256=self.policy.actor['content_sha256'],
            expected_upright_raw=self.reference[0], current_upright_raw=info.encoder_upright_raw,
            reference_firmware=self.reference[1], reference_matches=self._reference_matches(info),
            max_acceleration_m_s2=self.policy.actor['action_scale_m_s2'],
            default_duration_s=DEFAULT_DURATION_S, max_duration_s=60., guard_profile='rig',
            start_limits=START_LIMITS, run_limits=self.policy.run_limits,
            telemetry_rate_hz=rig.rate_hz, required_rate_hz=100,
            temporary_rate_change=rig.rate_hz != 100, hardware_accepted=False)

    def _validate_selection(self, rig):
        self._require_selected()
        rig._stopped_healthy()
        policy = self.validate_actor(self.path)
        if policy.actor['content_sha256'] != self.policy.actor['content_sha256']:
            raise ValidationError('selected actor file changed; reload with policy load PATH')
        if not self._reference_matches(rig.get_info()):
            raise ValidationError('saved encoder reference changed or is invalid; reload with policy load PATH')
        return policy

    def check(self, rig):
        policy = self._validate_selection(rig)
        # Compatibility is checked at the actual current rate without changing
        # or falsifying it. The inference runner still requires exactly 100 Hz.
        validate_live_executor(rig, policy, require_rate=False)
        if not self._reference_matches(rig.get_info()):
            raise ValidationError('saved encoder reference changed; reload with policy load PATH')
        policy.reset(rig.session)
        policy.validate_start(rig.control_observation())
        self.policy = policy  # Include any live-bound conservative rail limits.
        status = self.status(rig)
        if not status['reference_matches']:
            raise ValidationError('saved encoder reference changed; reload with policy load PATH')
        return dict(status, ready=True)

    def run(self, rig, *, execute, duration_s, output):
        if not math.isfinite(duration_s) or not .001 <= duration_s <= 60:
            raise ValidationError('policy duration must be finite and within .001..60 seconds')
        original_rate = rig.rate_hz
        rate_attempted = False
        # Deferral covers the bounded invocation and its STOP, then preserves
        # the caller's GC state when the interactive prompt becomes available.
        with defer_cyclic_gc():
            try:
                policy = self._validate_selection(rig)
                if original_rate != 100:
                    print(f'policy temporarily using 100 Hz telemetry (was {original_rate} Hz)', file=output, flush=True)
                    rate_attempted = True
                    rig.set_rate(100)
                scale = policy.actor['action_scale_m_s2']
                mode = 'run' if execute else 'shadow'
                print(f'DEVELOPMENT_ONLY balance-only {mode}: at most {duration_s:g}s; '
                      f'actor scale {scale:g} m/s²; rig rail/speed guards; '
                      f'saved upright reference {self.reference[0]}; Ctrl-C stops.', file=output, flush=True)
                return run_balance_policy(rig, self.path, expected_upright_raw=self.reference[0],
                    development_only=True, execute=execute, duration_s=duration_s,
                    max_acceleration=scale, guard_profile='rig',
                    expected_actor_sha256=policy.actor['content_sha256'])
            finally:
                try:
                    rig.stop()
                finally:
                    if rate_attempted:
                        pending_error = sys.exc_info()[0] is not None
                        try:
                            if rig.state.enabled:
                                raise ValidationError('rate restoration requires a disabled rig')
                            rig.set_rate(original_rate)
                        except Exception as error:
                            print(f'policy telemetry rate restoration failed: {error}; '
                                  f'current host rate {rig.rate_hz} Hz', file=output, flush=True)
                            if not pending_error:
                                raise
                        else:
                            print(f'policy restored telemetry to {original_rate} Hz', file=output, flush=True)

    def command(self, rig, args, output):
        if not args:
            raise ValidationError(HELP)
        operation, *values = args
        if operation == 'load' and len(values) == 1:
            self.load(rig, values[0])
            print(canonical_json(self.status(rig)), file=output)
        elif operation == 'status' and not values:
            print(canonical_json(self.status(rig)), file=output)
        elif operation == 'check' and not values:
            print(canonical_json(self.check(rig)), file=output)
        elif operation == 'unload' and not values:
            self.path = self.policy = self.reference = None
            self.invalidated = False
            print('learned policy unloaded', file=output)
        elif operation in ('run', 'shadow') and len(values) <= 1:
            duration = DEFAULT_DURATION_S if not values else float(values[0])
            result = self.run(rig, execute=operation == 'run', duration_s=duration, output=output)
            print(canonical_json(result), file=output)
        else:
            raise ValidationError(HELP)


def execute_policy_command(rig, args, output):
    if not hasattr(rig, '_console_policy'):
        rig._console_policy = ConsolePolicy()
    rig._console_policy.command(rig, args, output)
