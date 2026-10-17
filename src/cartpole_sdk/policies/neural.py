"""Bounded numeric PPO actor inference through the ordinary SDK Policy API.

Only a fixed two-layer tanh MLP is supported. No Torch, pickle, executable graph,
simulator, device object or automatic hardware source selection is loaded.
"""
from hashlib import sha256
import json
import math
from pathlib import Path

from cartpole_sdk.contracts import (Acceleration, Session, ValidationError,
    select_channels, validate_observation)
from cartpole_sdk.recording import strict_json_loads
from .rig_observation import SCHEMA as OBSERVATION_SCHEMA, QUANTITIES, encode_rig_observation

SCHEMA = 'cartpole-numeric-ppo-actor-v1'
RUNTIME_FILES = ('contracts.py', 'recording.py', 'policies/rig_observation.py', 'policies/neural.py')
MAX_BYTES = 1_000_000


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_actor(actor):
    if (not isinstance(actor, dict) or actor.get('schema') != SCHEMA or
            actor.get('observation_schema') != OBSERVATION_SCHEMA or
            actor.get('status') != 'DEVELOPMENT_ONLY' or actor.get('hardware_accepted') is not False or
            actor.get('rate_hz') != 100 or actor.get('angle_source') not in ('raw', 'filtered') or
            actor.get('feature_order') != ['age_s', 'state', 'valid']):
        raise ValidationError('unsupported numeric PPO actor contract')
    content = dict(actor)
    pin = content.pop('content_sha256', None)
    if _digest(content) != pin:
        raise ValidationError('numeric actor content hash mismatch')
    scale = actor.get('action_scale_m_s2')
    if type(scale) not in (float, int) or not math.isfinite(scale) or not 0 < scale <= 25:
        raise ValidationError('invalid numeric actor action scale')
    layers = actor.get('layers')
    if not isinstance(layers, list) or len(layers) != 3:
        raise ValidationError('expected fixed 21-64-64-1 actor')
    for layer, width, height, activation in zip(layers, (21, 64, 64), (64, 64, 1), ('tanh', 'tanh', 'identity')):
        if (not isinstance(layer, dict) or set(layer) != {'weights', 'bias', 'activation'} or
                layer['activation'] != activation or len(layer['weights']) != height or
                len(layer['bias']) != height or any(len(row) != width for row in layer['weights'])):
            raise ValidationError('invalid numeric actor layer shape')
        numbers = layer['bias'] + [value for row in layer['weights'] for value in row]
        if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e6 for value in numbers):
            raise ValidationError('invalid numeric actor coefficient')
    return actor


class NeuralPolicy:
    """Source-explicit reset(Session)/act(Observation) -> raw Acceleration."""
    def __init__(self, actor, *, channels):
        self.actor = validate_actor(actor)
        if type(channels) is not tuple or tuple(c.quantity for c in channels) != QUANTITIES:
            raise ValidationError('choose all six explicit encoder/governor channels')
        expected = 'magnetic' if actor['angle_source'] == 'raw' else 'magnetic_filtered'
        if channels[2].source not in (expected, 'simulation'):
            raise ValidationError('angle source differs from trained actor input')
        self.channels = channels
        self.rate_hz = 100
        self.session = None
        self.fault_reason = None
        self._previous = None

    def reset(self, session):
        if (not isinstance(session, Session) or session.topology.cart != self.channels[0].entity or
                session.topology.joints != (self.channels[2].entity,)):
            raise ValidationError('numeric actor requires configured cart and one pole')
        self.session, self.fault_reason, self._previous = session, None, None

    def predict_encoded(self, encoded):
        values = [float(value) for key in self.actor['feature_order'] for value in encoded[key]]
        if len(values) != 21 or not all(math.isfinite(value) for value in values):
            raise ValidationError('invalid actor features')
        for layer in self.actor['layers']:
            values = [bias + sum(w * x for w, x in zip(row, values))
                      for row, bias in zip(layer['weights'], layer['bias'])]
            if not all(math.isfinite(value) for value in values):
                raise ValidationError('nonfinite actor inference')
            if layer['activation'] == 'tanh':
                values = [math.tanh(value) for value in values]
        return max(-1., min(1., values[0])) * self.actor['action_scale_m_s2']

    def act(self, observation):
        if self.session is None:
            raise ValidationError('reset(Session) before inference')
        if self.fault_reason is not None:
            return None
        try:
            validate_observation(self.session, observation)
            now = observation.available_ns
            if self._previous is not None:
                sequence, previous_ns = self._previous
                if observation.sequence <= sequence or abs(now - previous_ns - 10_000_000) > 5_000_000:
                    raise ValidationError('replayed observation or incompatible 100 Hz cadence')
            samples = select_channels(observation, self.channels, now_ns=now, max_age_ns=20_000_000)
            if max(s.effective_ns for s in samples) - min(s.effective_ns for s in samples) > 10_000_000:
                raise ValidationError('sensor timestamp skew exceeds one control period')
            if samples[-1].value not in (-1, 0, 1):
                raise ValidationError('invalid brake direction')
            demand = self.predict_encoded(encode_rig_observation(observation, self.channels))
            self._previous = observation.sequence, now
            return Acceleration(demand)
        except ValidationError as exc:
            self.fault_reason = str(exc)
            return None


def load_neural_policy(path, *, channels):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError('numeric actor exceeds size limit')
    actor = validate_actor(strict_json_loads(raw.decode('utf-8')))
    root = Path(__file__).resolve().parents[1]
    expected = actor.get('runtime_sha256', {})
    if not isinstance(expected, dict) or set(expected) != set(RUNTIME_FILES):
        raise ValidationError('numeric actor lacks inference provenance')
    if any(sha256((root / name).read_bytes()).hexdigest() != expected[name] for name in RUNTIME_FILES):
        raise ValidationError('numeric actor inference source differs from saved provenance')
    return NeuralPolicy(actor, channels=channels)
