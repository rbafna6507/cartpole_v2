"""Validated rig parameters with measurement provenance kept alongside values."""
from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path


@dataclass
class RigConfig:
    arm_length_m: float = .125
    arm_mass_kg: float = .01105
    tip_mass_kg: float = .0117
    effective_length_m: float = .124454888
    damping_per_s: float = .913383
    coulomb_rad_s2: float = 0.0
    com_m: float = .09464285714285714
    cart_mass_kg: float = .5
    rail_half_m: float = .15
    max_velocity_m_s: float = .25
    max_acceleration_m_s2: float = 2.0
    max_jerk_m_s3: float = 20.0
    control_dt_s: float = .001
    policy_dt_s: float = .01
    encoder_counts: int = 4096
    encoder_upright_raw: int = 0
    sensor_noise_rad: float = 0.0
    actuator_time_constant_s: float = .01
    actuator_force_limit_n: float = 5.0
    seed: int = 0
    provenance: dict = field(default_factory=lambda: {
        'status': 'provisional', 'assembly_confirmed': False,
        'geometry_source': 'teensy_swingup_ethernet/teensy_swingup/teensy_swingup.ino',
        'dynamics_source': 'pendulum_characterization/125mm_11p05g/2026-09-15/controller_fit.json',
        'assumed_parameters': ['com_m', 'cart_mass_kg', 'actuator_time_constant_s',
                               'actuator_force_limit_n', 'sensor_noise_rad'],
        'note': 'Historical fit is a prior. Measure current assembly and validate a separate release.'})

    def __post_init__(self):
        nonnegative = {'tip_mass_kg', 'damping_per_s', 'coulomb_rad_s2', 'sensor_noise_rad'}
        integers = {'encoder_counts', 'encoder_upright_raw', 'seed'}
        for f in fields(self):
            if f.name == 'provenance':
                continue
            v = getattr(self, f.name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f'{f.name} must be finite numeric data')
            if f.name in integers:
                if not isinstance(v, int):
                    raise ValueError(f'{f.name} must be an integer')
            elif (v < 0 if f.name in nonnegative else v <= 0):
                raise ValueError(f'invalid {f.name}')
        if self.encoder_counts < 16 or not 0 <= self.encoder_upright_raw < self.encoder_counts:
            raise ValueError('invalid encoder count/reference')
        if not 0 <= self.seed < 2**32:
            raise ValueError('seed must be uint32')
        if not .03 <= self.rail_half_m <= .15:
            raise ValueError('commissioning rail half-span must be 0.03..0.15 m')
        if not self.com_m < self.effective_length_m:
            raise ValueError('effective length must exceed COM distance for positive body inertia')
        if self.com_m > self.arm_length_m:
            raise ValueError('COM must lie within the arm length')
        ratio = self.policy_dt_s / self.control_dt_s
        if ratio < 1 or not math.isclose(ratio, round(ratio), abs_tol=1e-8):
            raise ValueError('policy interval must be an integer multiple of control interval')
        if self.max_velocity_m_s > .25 or self.max_acceleration_m_s2 > 2 or self.max_jerk_m_s3 > 20:
            raise ValueError('configuration exceeds firmware commissioning ceilings')
        if not isinstance(self.provenance, dict):
            raise ValueError('provenance must be an object')

    @property
    def total_pendulum_mass_kg(self) -> float:
        return self.arm_mass_kg + self.tip_mass_kg

    @property
    def pivot_inertia_kg_m2(self) -> float:
        return self.total_pendulum_mass_kg * self.com_m * self.effective_length_m

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path) -> 'RigConfig':
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError('rig config must be a JSON object')
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f'unknown configuration fields: {sorted(unknown)}')
        return cls(**data)

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + '\n')
