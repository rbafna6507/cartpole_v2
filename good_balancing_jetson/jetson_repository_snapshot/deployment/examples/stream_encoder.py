"""Read-only local encoder stream; no arm, home or command is sent."""
import argparse
import json

from cartpole_deploy.hardware import HardwareRig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.50.2')
    parser.add_argument('--hz', type=int, default=100)
    parser.add_argument('--samples', type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.hz <= 500 or not 1 <= args.samples <= 100000:
        parser.error('hz must be 1..500 and samples 1..100000')
    with HardwareRig(host=args.host) as rig:
        rig.set_stream_rate(args.hz)
        for i, observation in enumerate(rig.iter_observations(), 1):
            print(json.dumps(observation.to_dict()), flush=True)
            if i >= args.samples:
                break


if __name__ == '__main__':
    main()
