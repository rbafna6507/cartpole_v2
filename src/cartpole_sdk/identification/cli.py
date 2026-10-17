"""Operator procedures for immutable collection, fitting and scoped simulation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


def parser():
    root=argparse.ArgumentParser(description=__doc__,epilog='Help and offline commands never open serial. See docs/system-identification-workflow.md for purpose, annotations and model limits.')
    commands=root.add_subparsers(dest='command')
    for name,purpose in (('inspect','Read saved reference, home, health and live parameters in a stopped session.'),
        ('collect-passive','Record operator-released oscillations with the motor disabled; physically restrain the cart.'),
        ('collect-pulse','Execute one allowlisted cart pulse then12s feedback hold; requires --execute.')):
        p=commands.add_parser(name,help=purpose,description=purpose)
        p.add_argument('--port',required=True,help='Explicit serial device; no discovery, home, clear or calibration.')
        p.add_argument('--output',type=Path,required=True,help='New immutable run directory, including failure evidence.')
        p.add_argument('--expected-reference',type=int,help='Optional exact saved upright raw encoder reference.')
        p.add_argument('--expected-home',type=int,help='Optional exact current home epoch.')
        if name!='inspect':
            camera=p.add_mutually_exclusive_group()
            camera.add_argument('--camera-url',default='http://127.0.0.1:3090/api/sensing-stream?max_hz=100',help='Raw sensing-stream URL; must become ready before serial collection.')
            camera.add_argument('--no-camera',action='store_true',help='Explicitly record missing independent camera evidence.')
        if name=='collect-passive':p.add_argument('--seconds',type=float,default=120.,help='Bounded1..180s; annotate hand-clear release intervals afterward.')
        if name=='collect-pulse':
            p.add_argument('--hold-seconds',type=float,default=12.,help='Explicit3..12s active cart feedback hold, default12s;20ms leases are unchanged.')
            p.add_argument('--execute',action='store_true',help='Authorize this invocation to issue ARM and acceleration requests.')
            p.add_argument('--amplitude-mm',type=int,required=True,choices=(-30,-20,-10,-5,5,10,20,30),help='Signed pulse amplitude; begin with5mm and inspect before escalating.')
    p=commands.add_parser('annotations-template',help='Create an explicit manual free-release annotation template; never select fit windows automatically.')
    p.add_argument('--input',required=True,help='Rig JSONL, JSONL.gz, or archive.tar.gz::exact/member.jsonl')
    p.add_argument('--output',required=True,type=Path)
    p=commands.add_parser('fit-passive',help='Fit training-only passive dynamics and score independently annotated validation releases.')
    p.add_argument('--training',required=True);p.add_argument('--training-annotations',type=Path,required=True)
    p.add_argument('--validation',required=True);p.add_argument('--validation-annotations',type=Path,required=True)
    p.add_argument('--model',choices=('viscous','viscous_coulomb'),default='viscous',help='Declare before examining validation; never select the winner from validation.')
    p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('fit-driven',help='Run the existing strict driven pendulum fitter using raw theta and MCU acceleration.')
    p.add_argument('--training',required=True);p.add_argument('--validation',required=True);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('assumptions-template',help='Create an editable complete provisional simulation configuration at100Hz; values remain assumptions.')
    p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('export-model',help='Export an accepted scoped fit with explicit assumptions; unsupported dynamics fail closed.')
    p.add_argument('--report',type=Path,required=True);p.add_argument('--scope',choices=('passive-down','driven'),required=True)
    p.add_argument('--assumptions',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('gym-smoke',help='Load an exported model and run a bounded headless zero-action check; no hardware/RL claim.')
    p.add_argument('--model',type=Path,required=True);p.add_argument('--steps',type=int,default=100)
    p.add_argument('--output',type=Path,required=True)
    return root


def main(argv=None):
    p=parser();args=p.parse_args(argv)
    if args.command is None:p.print_help();return 0
    if args.command=='collect-pulse' and not args.execute:p.error('collect-pulse requires explicit --execute')
    from . import workflow
    try:
        if args.output.exists():raise FileExistsError(f'output exists; preserve earlier evidence: {args.output}')
        if args.command in ('inspect','collect-passive','collect-pulse'):
            from .experiments import collect
            kind={'inspect':'inspect','collect-passive':'passive','collect-pulse':'pulse'}[args.command]
            camera_url=None if kind=='inspect' or getattr(args,'no_camera',False) else args.camera_url
            result=collect(kind,output=args.output,port=args.port,seconds=getattr(args,'seconds',120.),
                amplitude_m=getattr(args,'amplitude_mm',5)/1000,hold_seconds=getattr(args,'hold_seconds',12.),camera_url=camera_url,
                expected_reference=args.expected_reference,expected_home=args.expected_home,
                ready=lambda status:print(json.dumps(dict(output=str(args.output),**status)),flush=True))
            print(json.dumps(dict(output=str(args.output),completed=result['completed'],stop_confirmed=result.get('stop_confirmed'))));return 0
        if args.command=='annotations-template':result=workflow.annotation_template(args.input)
        elif args.command=='fit-passive':result=workflow.fit_passive_logs(args.training,args.training_annotations,args.validation,args.validation_annotations,model=args.model)
        elif args.command=='fit-driven':result=workflow.fit_driven_logs(args.training,args.validation)
        elif args.command=='assumptions-template':
            from cartpole_sdk.sim.config import SimulationConfig
            result=dict(simulation_config=asdict(SimulationConfig(control_steps=10)),rationale='',
                instructions='Review all assumed masses, force, rail and actuator limits; provide rationale. Export replaces only effective length and mapped hinge damping. control_steps=10 with1ms physics gives100Hz.')
        elif args.command=='export-model':
            result=workflow.export_model(workflow.read_json(args.report),scope=args.scope,
                assumptions=workflow.read_json(args.assumptions),output=args.output)
            print(json.dumps(dict(output=str(args.output),scope=result['acceptance_scope'],recommended_for_hardware_rl=False)));return 0
        else:result=workflow.gym_smoke(args.model,steps=args.steps)
        workflow.write_json(args.output,result)
        print(json.dumps(dict(output=str(args.output),accepted=result.get('accepted'),reasons=result.get('reasons',[]))))
        return 2 if result.get('accepted') is False else 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError) as exc:
        print(f'cartpole-id: {exc}',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
