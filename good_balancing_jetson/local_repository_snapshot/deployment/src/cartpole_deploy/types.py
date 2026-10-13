"""Shared observations: SI units, theta zero upright, positive towards +x."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Observation:
    time_us: int
    mode: str
    theta_rad: float
    omega_rad_s: float
    x_m: float
    v_m_s: float
    a_m_s2: float
    encoder_raw: int
    flags: int
    sequence: int
    session: int
    fault: str
    position_source: str = 'commanded_steps'

    @property
    def encoder_valid(self) -> bool:
        return bool(self.flags & 1)

    @property
    def homed(self) -> bool:
        return bool(self.flags & 2)

    @property
    def enabled(self) -> bool:
        return bool(self.flags & 4)

    def to_dict(self) -> dict:
        return asdict(self)
