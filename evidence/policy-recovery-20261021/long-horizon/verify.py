#!/usr/bin/env python3
"""Independent post-run trace audit; read fixed inputs, write new receipt/plots."""
from dataclasses import asdict
from hashlib import sha256
import json,math
from pathlib import Path
import numpy as np
from cartpole_sdk.control.parameters import ControllerParameters,gains
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def digest(p):return sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
    protocol=json.loads((HERE/'protocol.json').read_text());report=json.loads((HERE/'report.json').read_text())
    assert digest(HERE/'protocol.json')==report['protocol_sha256']
    assert digest(HERE/'run.py')==protocol['script_sha256']
    assert digest(HERE/'source.zip')==protocol['source_zip_sha256']
    for group in ('source_sha256','bindings'):
        for path,expected in protocol[group].items():assert digest(ROOT/path)==expected,path
    actor=ROOT/'training/candidates/balance-recovery-20261021/actor.json'
    policy=load_neural_policy(actor,channels=rig_channels(angle_source='filtered'));backend=NumpyActorBackend(policy.actor)
    assert policy.actor['content_sha256']==report['actor_content_sha256']
    g=gains(ControllerParameters(**protocol['experiment']['executor_parameters']),upright=True)
    teacher_max=actor_max=python_numpy_max=0.;rows_count=numpy_count=python_count=0;loaded=[];paired={}
    for episode in report['episodes']:
        path=HERE/episode['trace_path'];assert digest(path)==episode['trace_sha256']
        rows=[json.loads(line) for line in path.open()];assert len(rows)==episode['steps']
        key=(episode['seed'],episode['bias_degrees'])
        init=(episode['literal_initial_state'],episode['reset_truth'],episode['initial_encoded_observation'])
        if key in paired:assert paired[key]==init
        else:paired[key]=init
        for index,r in enumerate(rows):
            assert abs(r['t']-(index+1)*.01)<1e-9
            assert r['truth']['time_ns']==episode['reset_warmup_ns']+(index+1)*10_000_000
            q=r['truth'];balanced=abs(q['x'])<.12 and abs(q['theta'])<.15 and abs(q['omega'])<1.
            assert balanced==r['balanced']
            s=r['encoded_observation']['state']
            expected=max(-25.,min(25.,-g.k3*s[0]-g.k4*s[1]-g.k1*math.atan2(s[2],s[3])-g.k2*s[4]))
            teacher_max=max(teacher_max,abs(expected-r['analytic_BAL_on_same_observation_m_s2']))
            if episode['arm']=='analytic_BAL_filtered':
                assert abs(expected-r['raw_command_m_s2'])<1e-10
            else:
                predicted=backend.predict_encoded(r['encoded_observation']);numpy_count+=1
                actor_max=max(actor_max,abs(predicted-r['raw_command_m_s2']))
                if index%100==0 or index==len(rows)-1:
                    python_numpy_max=max(python_numpy_max,abs(policy.predict_encoded(r['encoded_observation'])-predicted));python_count+=1
            rows_count+=1
        for metric in episode['horizons']:
            selected=rows[:round(metric['horizon_s']*100)];n=len(selected)
            assert metric['steps']==n
            if not n:continue
            dwell=0
            for r in reversed(selected):
                if not r['balanced']:break
                dwell+=1
            assert abs(metric['final_balance_dwell_s']-dwell*.01)<1e-9
            assert metric['hold_success']==(n==round(metric['horizon_s']*100) and metric['fault'] is None and dwell>=500)
            assert abs(metric['max_abs_x_m']-max(abs(r['truth']['x']) for r in selected))<1e-12
            expected_rms=math.degrees(math.sqrt(sum(r['truth']['theta']**2 for r in selected[-500:])/len(selected[-500:])))
            assert abs(metric['tail_theta_rms_deg']-expected_rms)<1e-10
        loaded.append((episode,rows))
    assert len(loaded)==protocol['trajectories']==24
    assert teacher_max<1e-10 and actor_max<1e-10 and python_numpy_max<=1e-5
    audit=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,all_checks_pass=True,
        report_sha256=digest(HERE/'report.json'),verification_script_sha256=digest(Path(__file__)),
        trajectories=len(loaded),trace_rows=rows_count,matched_initial_conditions=len(paired),
        all_trace_hashes_verified=True,all_bound_source_actor_checkpoint_hashes_verified=True,
        independently_verified=['literal matched starts/reset/first observation','100Hz trace timing','true-state balance and final dwell','25s/60s success and max excursion','final5s theta RMS','analytic BAL command using actual gains(upright=True)','all MLP numeric commands','sampled normal strict Python versus NumPy backend'],
        max_analytic_command_discrepancy_m_s2=teacher_max,mlp_numpy_replayed_commands=numpy_count,
        max_mlp_replay_discrepancy_m_s2=actor_max,strict_python_samples=python_count,
        max_strict_python_numpy_discrepancy_m_s2=python_numpy_max)
    write(HERE/'verification.json',audit)
    attribution=[]
    for episode,rows in loaded:
        attribution.append(dict(arm=episode['arm'],seed=episode['seed'],bias_degrees=episode['bias_degrees'],
            x_outside_hold_steps=sum(abs(r['truth']['x'])>=.12 for r in rows),
            theta_outside_hold_steps=sum(abs(r['truth']['theta'])>=.15 for r in rows),
            omega_outside_hold_steps=sum(abs(r['truth']['omega'])>=1. for r in rows)))
    gain_ratio=g.k1/g.k3
    analysis=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,
        report_sha256=digest(HERE/'report.json'),verification_sha256=digest(HERE/'verification.json'),
        ideal_static_offset_model=dict(equation='x_eq=-(k_theta/k_x)*encoder_bias_rad when true theta=omega=v=0 and no nonlinear/quantization effects',
            gain_ratio_m_per_rad=gain_ratio,offset_m_per_positive_degree=-gain_ratio*math.pi/180.,
            scope='Analytic equilibrium approximation only; actual nonlinear trajectory metrics determine the observed centering and hold result.'),
        balance_failure_components=attribution,
        interpretation='All failures remain in the record. Constant offset tests isolate sensitivity inside this fixed model; they do not identify hardware calibration or physical sensor failure.',
        plots=['trajectories-60s.png','oscillation-final5s.png'])
    write(HERE/'analysis.json',analysis)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'analytic_BAL_filtered':'#777777','MLP_BAL_filtered':'#1675b7'}
    for zoom,filename in ((False,'trajectories-60s.png'),(True,'oscillation-final5s.png')):
        fig,axes=plt.subplots(3,2,figsize=(11,8),sharex=True)
        for rowindex,bias in enumerate(protocol['bias_degrees']):
            for episode,rows in loaded:
                if episode['bias_degrees']!=bias:continue
                selected=[r for r in rows if not zoom or r['t']>=55.]
                t=[r['t'] for r in selected];color=colors[episode['arm']]
                label=episode['arm'].replace('_filtered','') if episode['seed']==97410 else None
                axes[rowindex,0].plot(t,[r['truth']['x']*1000 for r in selected],color=color,alpha=.7,lw=.8,label=label)
                axes[rowindex,1].plot(t,[math.degrees(r['truth']['theta']) for r in selected],color=color,alpha=.7,lw=.8,label=label)
            for limit in (-120.,120.):axes[rowindex,0].axhline(limit,color='#b03a2e',ls='--',lw=.7)
            for limit in (-math.degrees(.15),math.degrees(.15)):axes[rowindex,1].axhline(limit,color='#b03a2e',ls='--',lw=.7)
            axes[rowindex,0].set_ylabel(f'Bias {bias:+.0f}°\nTrue cart (mm)')
            axes[rowindex,1].set_ylabel('True angle (°)')
            for ax in axes[rowindex]:ax.grid(alpha=.2)
        axes[0,0].legend(fontsize=8,loc='upper right');axes[0,0].set_title('Centering');axes[0,1].set_title('Pole angle')
        for ax in axes[-1]:ax.set_xlabel('Time after causal reset warmup (s)')
        fig.suptitle('Frozen filtered BAL teacher vs learned approximation — four fresh starts each\nUnchanged provisional model; development sensitivity only',fontsize=12)
        fig.tight_layout(rect=(0,0,1,.94));fig.savefig(HERE/filename,dpi=160);plt.close(fig)
    print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
