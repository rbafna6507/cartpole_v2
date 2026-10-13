import json,sys,unittest,math
from pathlib import Path
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision import Tracker
from train_state import CartPoleEnv
from cartpole_model import make_mjcf,link_properties
import mujoco
class Tests(unittest.TestCase):
 def test_vision_home_sign_loss(self):
  cfg=json.loads((Path(__file__).resolve().parents[1]/'tracker.json').read_text());v=Tracker(cfg)
  def frame(x=160,y=200,extra=False):
   f=np.zeros((300,320,3),np.uint8);cv2.circle(f,(160,100),7,(0,255,0),-1);cv2.circle(f,(x,y),7,(255,0,0),-1)
   if extra:cv2.circle(f,(250,250),7,(255,0,0),-1)
   return f
  for i in range(30):v.process(frame(),i*.0125)
  v.home();s=v.process(frame(),.4);self.assertAlmostEqual(s['theta_down_rad'],0)
  s=v.process(frame(210,187),.4125);self.assertGreater(s['theta_down_rad'],0);self.assertLess(s['theta_upright_rad'],math.pi)
  self.assertFalse(v.process(frame(extra=True),.425)['valid'])
  self.assertIsNone(v.process(frame(),.4375)['omega_rad_s'])
 def test_period(self):
  prop=link_properties(length=.125,rod_mass=.01105,tip_mass=.0117)
  m=mujoco.MjModel.from_xml_string(make_mjcf(locked_cart=True,link_length=.125,link_mass=.01105,tip_mass=.0117));d=mujoco.MjData(m);d.qpos[0]=math.pi+.03
  crossings=[];old=.03
  for _ in range(12000):
   mujoco.mj_step(m,d);new=d.qpos[0]-math.pi
   if old<0<=new:crossings.append(d.time)
   old=new
  self.assertAlmostEqual(float(np.mean(np.diff(crossings))),prop['period'],delta=.002)
 def test_limits_seed(self):
  e=CartPoleEnv();o,_=e.reset(seed=1);q,_=e.reset(seed=1);np.testing.assert_equal(o,q)
  for _ in range(100):
   _,_,term,trunc,_=e.step(np.array([1.]));self.assertLessEqual(abs(e.v_command),e.v_max+1e-9)
   if term or trunc:break
  e.close()
if __name__=='__main__':unittest.main()
