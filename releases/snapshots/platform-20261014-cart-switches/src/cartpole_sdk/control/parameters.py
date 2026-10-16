"""Saved candidate controller settings, independent of rig calibration."""
from dataclasses import dataclass, fields
from importlib.resources import files
import json
import math

@dataclass(frozen=True)
class ControllerParameters:
    leff: float = .124
    pw: float = 4.5
    pz: float = .85
    bal_pw: float = 4.0
    pc1: float = -3.0
    pc2: float = -4.0
    vmax: float = 1.5
    vmax_s: float = 1.5
    vmax_b: float = 1.5
    approach_v: float = .3
    catch_v: float = .3
    approach_angle: float = .8
    catch_da: float = 4.0
    amax_s: float = 25.0
    amax_b: float = 25.0
    jmax: float = 150.0
    amax_m: float = .5
    jmax_m: float = 10.0
    ke: float = 4.0
    kpx: float = 40.0
    kdx: float = 2.0
    phase_soft: float = 2.0
    catch_a: float = .6
    catch_r: float = 3.0
    giveup: float = .8
    spin_trip_rad_s: float = 150.0
    spin_resume_rad_s: float = 10.0
    rail: float = .26
    bw: float = 30.0
    vman: float = .05

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{f.name} must be finite numeric')
        positive = ('leff','pw','bal_pw','pz','vmax','vmax_s','vmax_b','approach_v','catch_v','approach_angle','catch_da','amax_s','amax_b','jmax','amax_m','jmax_m','phase_soft','catch_a','catch_r','giveup')
        if any(getattr(self, key) <= 0 for key in positive):
            raise ValueError('physical/controller limits must be positive')
        if self.rail <= .02 or not .1 <= self.bw <= 100:
            raise ValueError('rail or estimator bandwidth outside supported range')
        if not 0 < self.spin_resume_rad_s < self.spin_trip_rad_s:
            raise ValueError('spin limits require 0 < resume < trip')

@dataclass(frozen=True)
class Gains:
    k1: float
    k2: float
    k3: float
    k4: float

def load_tuned_parameters() -> ControllerParameters:
    preset = json.loads(files(__package__).joinpath('tuned_parameters.json').read_text())
    return ControllerParameters(**{f.name: preset['settings'][f.name] for f in fields(ControllerParameters)})

def gains(p: ControllerParameters, upright: bool = False) -> Gains:
    pw = p.bal_pw if upright else p.pw
    b1, b0 = 2*p.pz*pw, pw*pw
    c1, c0 = -(p.pc1+p.pc2), p.pc1*p.pc2
    k3 = -b0*c0*p.leff/9.81
    k4 = -(b1*c0+b0*c1)*p.leff/9.81
    k1 = p.leff*k3-9.81-p.leff*(b0+b1*c1+c0)
    k2 = p.leff*(k4-b1-c1)
    return Gains(k1,k2,k3,k4)
