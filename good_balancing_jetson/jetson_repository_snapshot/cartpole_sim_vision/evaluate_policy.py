"""Simulation evaluation and schematic animation; no OpenGL/camera required."""
import json
import numpy as np
from stable_baselines3 import PPO
from train_state import CartPoleEnv

def evaluate(prefix='balance',episodes=30):
    cfg=json.load(open(prefix+'_config.json'));env=CartPoleEnv(**cfg);model=PPO.load(prefix,device='cpu')
    reports=[];trace=[]
    for seed in range(1000,1000+episodes):
        obs,_=env.reset(seed=seed);done=False;up=0;count=0;ep=[]
        while not done:
            act,_=model.predict(obs,deterministic=True)
            obs,r,term,trunc,info=env.step(act);done=term or trunc
            count+=1;up+=info['upright'];ep.append([env.data.time,*env.data.qpos])
        reports.append(dict(seed=seed,duration_s=float(env.data.time),failed=bool(term),upright_fraction=up/count))
        if not trace:trace=ep
    env.close()
    summary=dict(episodes=episodes,survival_fraction=float(np.mean([not r['failed'] for r in reports])),mean_upright_fraction=float(np.mean([r['upright_fraction'] for r in reports])),episodes_detail=reports)
    with open(prefix+'_evaluation.json','w') as f:json.dump(summary,f,indent=2)
    return summary,np.array(trace)

def animate(trace,length=.125,stop=.18):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    fig,ax=plt.subplots(figsize=(9,4));ax.set(xlim=(-.25,.25),ylim=(-length*1.2,length*1.2),xlabel='Position (m)',ylabel='Height relative to pivot (m)');ax.set_aspect('equal');ax.axhline(0,color='gray')
    ax.axvline(-stop,color='red',ls=':');ax.axvline(stop,color='red',ls=':')
    line,=ax.plot([],[],'o-',lw=3);title=ax.set_title('')
    def update(i):
        t,x,theta=trace[i];line.set_data([x,x+length*np.sin(theta)],[0,length*np.cos(theta)]);title.set_text(f'Simulated policy, t={t:.2f}s');return line,title
    animation=FuncAnimation(fig,update,frames=range(0,len(trace),2),interval=25,blit=False);plt.close(fig);return animation
