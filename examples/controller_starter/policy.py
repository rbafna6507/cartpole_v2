"""Upload this file unchanged after local simulation/replay. Illustrative damping only."""
from cartpole_sdk import Acceleration, ValidationError
from cartpole_sdk.developer import ObservationAdapter


class Controller:
    def __init__(self):
        # Explicitly support these two source contracts. Never relabel observations.
        self.adapter = ObservationAdapter(angle_source='filtered',
                                          sources=('simulation', 'magnetic-step'))

    def reset(self, session):
        self.adapter.reset(session)
        self.previous = None
        self.fault_reason = None

    def act(self, observation):
        if self.fault_reason is not None:
            return None
        try:
            x, velocity, angle, rate, acceleration, brake = self.adapter.select(observation)
            if self.previous is not None:
                sequence, stamp = self.previous
                if observation.sequence <= sequence or abs(observation.available_ns - stamp - 10_000_000) > 5_000_000:
                    raise ValidationError('repeated sample or incompatible 100 Hz cadence')
            self.previous = observation.sequence, observation.available_ns
            return Acceleration(max(-.25, min(.25, -2. * velocity.value)))
        except ValidationError as exc:
            self.fault_reason = str(exc)
            return None


def create_policy():
    return Controller()
