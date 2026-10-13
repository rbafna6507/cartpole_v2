"""Single-link perfect-state PPO starter. SIMULATION ONLY; no serial/camera code.
Drive defaults are placeholders. No delay/noise/randomization: establish a clean
baseline, then implement measured observation/actuation timing before transfer.
"""
import argparse
import json
import numpy as np
import mujoco
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from cartpole_model import make_mjcf


class CartPoleEnv(gym.Env):
    def __init__(self,task='balance',sysid=None,v_max=.25,a_max=1.,servo_kv=20.,force_max=2.,cart_mass=.5,link_length=.125,link_mass=.01105,tip_mass=.0117,rail_limit=.2):
        super().__init__()
        if task not in ('balance','swingup'): raise ValueError('unknown task')
        if rail_limit<=.04: raise ValueError('rail half travel must exceed .04 m')
        if min(v_max,a_max,force_max,cart_mass)<=0: raise ValueError('limits/mass must be positive')
        self.rail_stop=rail_limit-.02; self.link_length=link_length
        self.task=task; self.v_max=v_max; self.a_max=a_max
        self.model=mujoco.MjModel.from_xml_string(make_mjcf(sysid=sysid,v_max=v_max,servo_kv=servo_kv,force_max=force_max,cart_mass=cart_mass,link_length=link_length,link_mass=link_mass,tip_mass=tip_mass,rail_limit=rail_limit))
        self.data=mujoco.MjData(self.model)
        self.substeps=25 # 0.5 ms physics, 12.5 ms policy = 80 Hz
        self.dt=self.substeps*self.model.opt.timestep
        self.action_space=spaces.Box(-1.,1.,shape=(1,),dtype=np.float32)
        # x/self.rail_stop, xdot/vmax, sin(theta), cos(theta), omega/20, v_command/vmax
        self.observation_space=spaces.Box(-np.inf,np.inf,shape=(6,),dtype=np.float32)
        self.v_command=0.; self.steps=0; self.previous_action=0.

    def observation(self):
        x,theta=self.data.qpos; v,omega=self.data.qvel
        return np.array([x/self.rail_stop,v/self.v_max,np.sin(theta),np.cos(theta),omega/20,self.v_command/self.v_max],dtype=np.float32)

    def reset(self,seed=None,options=None):
        super().reset(seed=seed); mujoco.mj_resetData(self.model,self.data)
        self.data.qpos[:]=[self.np_random.uniform(-.02,.02), (0. if self.task=='balance' else np.pi)+self.np_random.uniform(-.08,.08)]
        self.data.qvel[:]=self.np_random.uniform(-.02,.02,2)
        self.v_command=0.; self.steps=0; self.previous_action=0.
        mujoco.mj_forward(self.model,self.data)
        return self.observation(),{}

    def step(self,action):
        if not np.isfinite(action).all(): raise ValueError('nonfinite action')
        u=float(np.clip(action[0],-1,1))
        for _ in range(self.substeps):
            self.v_command=float(np.clip(self.v_command+u*self.a_max*self.model.opt.timestep,-self.v_max,self.v_max))
            self.data.ctrl[0]=self.v_command
            mujoco.mj_step(self.model,self.data)
            if abs(self.data.qpos[0])>=self.rail_stop: break
        self.steps+=1
        x,theta=self.data.qpos; _,omega=self.data.qvel
        wrapped=np.arctan2(np.sin(theta),np.cos(theta))
        upright=abs(wrapped)<.15 and abs(omega)<1.
        reward=float(np.cos(theta)-.2*(x/self.rail_stop)**2-.001*omega**2-.01*u*u-.01*(u-self.previous_action)**2+.5*upright)
        failed=abs(x)>=self.rail_stop or (self.task=='balance' and abs(wrapped)>.6)
        if failed: reward-=5.
        self.previous_action=u
        return self.observation(),reward,bool(failed),self.steps>=800,{'upright':bool(upright),'x_m':float(x)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--task',choices=['balance','swingup'],default='balance')
    p.add_argument('--steps',type=int,default=1_000_000)
    p.add_argument('--out',default='policy')
    p.add_argument('--load',help='continue training a compatible policy zip')
    p.add_argument('--sysid')
    p.add_argument('--config',default='simulation.json')
    p.add_argument('--v-max',type=float,default=.25); p.add_argument('--a-max',type=float,default=1.)
    p.add_argument('--servo-kv',type=float,default=20.); p.add_argument('--force-max',type=float,default=2.)
    p.add_argument('--cart-mass',type=float,default=.5)
    p.add_argument('--smoke',action='store_true',help='API check plus short training/evaluation, not learning validation')
    pre,_=p.parse_known_args()
    defaults=json.load(open(pre.config))['environment'] if pre.config else {}
    p.set_defaults(**{k:v for k,v in defaults.items() if k in ('v_max','a_max','servo_kv','force_max','cart_mass')})
    a=p.parse_args(); fitted=None
    if a.sysid:
        with open(a.sysid) as f: fitted=json.load(f)
    config=dict(task=a.task,sysid=fitted,v_max=a.v_max,a_max=a.a_max,servo_kv=a.servo_kv,force_max=a.force_max,cart_mass=a.cart_mass)
    from pathlib import Path
    if a.config:
        base=json.load(open(a.config)); config.update({k:v for k,v in base['environment'].items() if k not in ('v_max','a_max','servo_kv','force_max','cart_mass')})
        config['task']=a.task
        if fitted is not None: config['sysid']=fitted
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    env=CartPoleEnv(**config); check_env(env)
    agent=PPO.load(a.load,env=env) if a.load else PPO('MlpPolicy',env,verbose=1,seed=0,n_steps=256,batch_size=64,device='cpu')
    agent.learn(total_timesteps=512 if a.smoke else a.steps)
    agent.save(a.out)
    with open(a.out+'_config.json','w') as f: json.dump(config,f,indent=2)
    evaluation=CartPoleEnv(**config); report=[]
    for seed in range(100,105):
        obs,_=evaluation.reset(seed=seed); done=False; score=0.; upright=0; count=0
        while not done:
            action,_=agent.predict(obs,deterministic=True)
            obs,r,terminated,truncated,info=evaluation.step(action)
            done=terminated or truncated; score+=r; upright+=info['upright']; count+=1
        report.append(dict(seed=seed,reward=score,duration_s=evaluation.data.time,upright_fraction=upright/count,failed=terminated))
    with open(a.out+'_eval.json','w') as f: json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
    env.close(); evaluation.close()


if __name__=='__main__': main()
