"""One bounded controller loop using the simulation or commissioned hardware SDK.

Simulation by default. Hardware use requires all explicit commissioning flags.
This demo makes a slow 3 mm cart motion; it is not a balancing controller.
"""
import argparse
import math
import time

from cartpole_deploy.config import RigConfig


def controller(observation, elapsed_s):
    """Replace this body with a controller; return an SI action intent."""
    target = .003*math.sin(2*math.pi*.3*elapsed_s)*math.sin(math.pi*elapsed_s/4)**2 if elapsed_s < 4 else 0
    return 'position', target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--center-confirmed', action='store_true')
    parser.add_argument('--secured-z', action='store_true')
    parser.add_argument('--measured-half-span-m', type=float)
    parser.add_argument('--host', default='192.168.50.2')
    args = parser.parse_args()
    if args.hardware and not (args.execute and args.center_confirmed and args.secured_z
                              and args.measured_half_span_m is not None):
        parser.error('hardware motion requires --execute --center-confirmed --secured-z --measured-half-span-m')
    config = RigConfig(rail_half_m=args.measured_half_span_m if args.hardware else .15)
    if args.hardware:
        from cartpole_deploy.hardware import HardwareRig
        rig = HardwareRig(host=args.host)
    else:
        from cartpole_deploy.simulation import SimRig
        rig = SimRig(config)
    with rig:
        state = rig.read()
        if state.mode != 'DISARMED' or state.enabled:
            raise RuntimeError('requires a disabled, fault-free rig')
        rig.home(config.rail_half_m)
        try:
            rig.arm()
            start = time.monotonic()
            for i in range(501):
                if i:
                    if args.hardware:
                        time.sleep(max(0, start+i*.01-time.monotonic()))
                    else:
                        rig.advance(.01)
                observation = rig.read()
                if observation.mode == 'FAULT':
                    raise RuntimeError(observation.fault)
                kind, value = controller(observation, i*.01)
                rig.command(kind, value, ttl_ms=50)
                if i % 50 == 0:
                    print(observation.to_dict())
        finally:
            rig.stop()


if __name__ == '__main__':
    main()
