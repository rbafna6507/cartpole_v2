#!/usr/bin/env python3
"""Bounded exploratory observed-state balance-law screen; no hardware approval.

The six fixed laws are evaluated on upright development poses, nominal and
fixed +/-1 degree actor-input bias. Core plant, sensing and governor are read
only. This is a diagnostic baseline, not neural training or an SDK export.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path
import time

import numpy as np

from cartpole_sdk.learning.diagnostics import preserved_rng
from cartpole_sdk.learning.model_experiment import validate_experiment
from cartpole_sdk.learning.ppo import TrainingEnv, _write_new, experiment_identity, provenance

CANDIDATES = [dict(name=f'x{x:g}-v{v:g}-theta40-w{w:g}', gains=[x,v,40.,w])
    for x,v,w in ((1.,2.,2.), (4.,4.,2.), (8.,4.,2.),
                  (8.,6.,3.), (12.,4.,2.), (12.,6.,3.))]
SCENARIOS = [('nominal',0.), ('angle-minus1deg',-math.pi/180),
             ('angle-plus1deg',math.pi/180)]
INITIAL_SEEDS = (58000,58001)
CONFIRMATION_SEEDS = (58100,58101,58102,58103)


def demand(observation, gains, offset, limit):
    x,v,s,c,omega,_,_ = map(float,observation['state'])
    theta = math.atan2(s,c)+offset
    theta = math.atan2(math.sin(theta),math.cos(theta))
    raw = gains[0]*x+gains[1]*v+gains[2]*theta+gains[3]*omega
    return max(-limit,min(limit,raw)),theta


def eligible(episodes, *, expected):
    return len(episodes)==expected and all(row['hold_success'] for row in episodes)


def sources():
    return dict(runtime=provenance(), script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        rng_helper_sha256=sha256(Path(__file__).resolve().parents[1].joinpath(
            'src/cartpole_sdk/learning/diagnostics.py').read_bytes()).hexdigest())


def episode(experiment, candidate, seed, scenario, stage, output):
    name,offset = scenario
    env = TrainingEnv(experiment,(seed,))
    observation,_ = env.reset(options=dict(episode_seed=seed,start='upright'))
    relative = f'traces/{stage}-{candidate["name"]}-{name}-{seed}.jsonl.gz'
    reset_ns = env.core.ground_truth.time_ns
    raw_actions, final_window = [],[]
    started=time.monotonic()
    try:
        with gzip.open(output/relative,'xt') as stream:
            while True:
                raw,theta = demand(observation,candidate['gains'],offset,env.action_scale)
                before = {key:value.tolist() for key,value in observation.items()}
                observation,_,terminated,truncated,_ = env.step([raw/env.action_scale])
                truth = asdict(env.core.ground_truth)
                row=dict(step=env.steps,elapsed_s=(truth['time_ns']-reset_ns)/1e9,
                    observed_before_action=before,observed_theta_with_bias_rad=theta,
                    raw_action_m_s2=raw,ground_truth_after=truth,
                    actual_executor_raw_m_s2=env.core.diagnostics.raw_acceleration_m_s2,
                    executed_acceleration_m_s2=env.core.diagnostics.executed_acceleration_m_s2,
                    fault_reason=env.fault,terminal=bool(terminated or truncated))
                stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
                raw_actions.append(raw)
                if row['elapsed_s']>experiment['simulation_config']['max_steps']/100.-5.:
                    final_window.append(truth)
                if terminated or truncated:
                    break
        result=env.result(hold_seconds=5.)
        final_complete=result['final_window_complete']
        result.update(stage=stage,candidate=candidate['name'],gains=candidate['gains'],
            scenario=name,angle_bias_rad=offset,trace_path=relative,
            trace_sha256=sha256((output/relative).read_bytes()).hexdigest(),
            final_window_mean_x_m=float(np.mean([r['x'] for r in final_window])) if final_complete else None,
            final_window_x_rms_m=float(np.sqrt(np.mean([r['x']**2 for r in final_window]))) if final_complete else None,
            raw_action_rms_m_s2=float(np.sqrt(np.mean(np.square(raw_actions)))),
            approximate_static_x_if_true_theta_zero_m=-candidate['gains'][2]*offset/candidate['gains'][0],
            wall_seconds=time.monotonic()-started)
        return result
    finally:
        env.close()


def aggregate(episodes, candidate, stage):
    rows=[row for row in episodes if row['candidate']==candidate['name'] and row['stage']==stage]
    return dict(candidate=candidate['name'],gains=candidate['gains'],stage=stage,episodes=len(rows),
        hold_successes=sum(row['hold_success'] for row in rows),
        faults=sum(row['fault_reason'] is not None for row in rows),
        max_abs_x_m=max(row['max_abs_x_m'] for row in rows),
        mean_raw_action_rms_m_s2=float(np.mean([row['raw_action_rms_m_s2'] for row in rows])),
        by_scenario={name:dict(episodes=sum(row['scenario']==name for row in rows),
            holds=sum(row['hold_success'] for row in rows if row['scenario']==name),
            max_abs_x_m=max(row['max_abs_x_m'] for row in rows if row['scenario']==name))
            for name,_ in SCENARIOS})


def run(run_path, output, *, seconds=25.):
    run_path,output=Path(run_path).resolve(),Path(output)
    raw_recipe=(run_path/'recipe.json').read_bytes()
    raw_report=(run_path/'report.json').read_bytes()
    original=json.loads(raw_recipe); training_report=json.loads(raw_report)
    if sha256(raw_recipe).hexdigest()!=training_report['recipe_sha256']:
        raise ValueError('source run recipe hash mismatch')
    if any(training_report.get(key)!=value for key,value in original.items()):
        raise ValueError('source run metadata mismatch')
    if (not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or
            not 5<=seconds<=60 or not math.isclose(seconds*100,round(seconds*100))):
        raise ValueError('seconds must be whole 100 Hz decisions in 5..60')
    experiment=deepcopy(original['experiment'])
    experiment['simulation_config']['max_steps']=round(seconds*100)
    validate_experiment(experiment)
    pins=sources()
    recipe=dict(schema='cartpole-centering-bias-screen-v1',status='DEVELOPMENT_ONLY',
        simulation_only=True,hardware_accepted=False,deployable=False,
        experiment=experiment,experiment_sha256=experiment_identity(experiment),
        source_run=str(run_path),source_run_recipe_sha256=sha256(raw_recipe).hexdigest(),
        source_run_report_sha256=sha256(raw_report).hexdigest(),evaluation_source=pins,
        candidates=CANDIDATES,scenarios=[dict(name=name,angle_bias_rad=bias) for name,bias in SCENARIOS],
        seconds=seconds,initial_development_seeds=INITIAL_SEEDS,confirmation_seeds=CONFIRMATION_SEEDS,
        start='upright',law='clip(kx*x + kv*v + ktheta*atan2(sin(theta+bias),cos(theta+bias)) + komega*omega)',
        input_scope='Observed x,v,encoder angle/rate only. Bias changes actor angle only; plant, zero, rate, validity and governor unchanged.',
        metric_scope='Full horizon with no fault; final five seconds of successive 100 Hz samples abs(theta)<.15,abs(omega)<1,abs(x)<.12.',
        selection='Only candidates passing all six initial episodes qualify. Among them choose minimum worst max_abs_x, then mean raw action RMS; evaluate that one on four fresh poses, all three scenarios.',
        limitations='Fixed engineering bias, not measured uncertainty. Development selection only, no neural training, no SDK export or hardware claim.')
    output.mkdir(parents=True,exist_ok=False);(output/'traces').mkdir()
    _write_new(output/'recipe.json',recipe)
    (output/'source.py').write_bytes(Path(__file__).read_bytes())
    (output/'source-run-recipe.json').write_bytes(raw_recipe)
    episodes=[];summaries=[];winner=None
    with preserved_rng():
        for candidate in CANDIDATES:
            for seed in INITIAL_SEEDS:
                for scenario in SCENARIOS:
                    episodes.append(episode(experiment,candidate,seed,scenario,'initial',output))
            summary=aggregate(episodes,candidate,'initial');summaries.append(summary)
            print(json.dumps(summary,allow_nan=False),flush=True)
            (output/'progress.json').write_text(json.dumps(dict(completed=False,summaries=summaries),indent=2)+'\n')
        qualified=[summary for summary in summaries if eligible(
            [row for row in episodes if row['candidate']==summary['candidate']],expected=6)]
        if qualified:
            best=min(qualified,key=lambda row:(row['max_abs_x_m'],row['mean_raw_action_rms_m_s2']))
            winner=next(candidate for candidate in CANDIDATES if candidate['name']==best['candidate'])
            for seed in CONFIRMATION_SEEDS:
                for scenario in SCENARIOS:
                    episodes.append(episode(experiment,winner,seed,scenario,'confirmation',output))
            summary=aggregate(episodes,winner,'confirmation');summaries.append(summary)
            print(json.dumps(summary,allow_nan=False),flush=True)
    if sources()!=pins or (run_path/'recipe.json').read_bytes()!=raw_recipe or (run_path/'report.json').read_bytes()!=raw_report:
        raise ValueError('source/runtime changed during screen; no final report')
    report=dict(schema='cartpole-centering-bias-screen-report-v1',completed=True,
        status='DEVELOPMENT_ONLY',hardware_accepted=False,deployable=False,
        recipe_sha256=sha256((output/'recipe.json').read_bytes()).hexdigest(),
        evaluation_source=pins,episodes=episodes,summaries=summaries,selected=winner,
        confirmation_pass=eligible([row for row in episodes if row['stage']=='confirmation'],expected=12),
        selection_scope='Exploratory upright development screen; all failures retained; no swing-up claim.')
    _write_new(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=25.)
    args=parser.parse_args()
    run(args.run,args.output,seconds=args.seconds)
