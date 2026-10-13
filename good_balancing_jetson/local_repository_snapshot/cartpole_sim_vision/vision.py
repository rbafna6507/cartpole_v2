"""Color marker pose POC. Image x right, y down. No hardware commands."""
import math
from collections import deque
import cv2
import numpy as np

def wrap(a): return math.atan2(math.sin(a),math.cos(a))

def blob(frame,bounds,cfg):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,np.array(bounds[0],np.uint8),np.array(bounds[1],np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[c for c in contours if cfg['min_area_px']<=cv2.contourArea(c)<=cfg['max_area_px']]
    # Ambiguity invalidates rather than choosing a different object silently.
    if len(candidates)!=1:return None
    m=cv2.moments(candidates[0]);return (m['m10']/m['m00'],m['m01']/m['m00'])

class Tracker:
    def __init__(self,cfg):
        self.cfg=cfg;self.history=deque(maxlen=cfg['home_samples']);self.previous=None
    def home(self):
        if len(self.history)<self.history.maxlen:raise ValueError('Hold hanging still with both markers visible until 30 valid frames accumulate')
        a=np.array([h[0] for h in self.history]);mean=math.atan2(np.sin(a).mean(),np.cos(a).mean())
        if max(abs(wrap(x-mean)) for x in a)>math.radians(self.cfg['home_max_spread_deg']):raise ValueError('Pendulum is moving: hold hanging still')
        self.cfg['home_angle_rad']=mean;self.cfg['home_length_px']=float(np.median([h[1] for h in self.history]));self.previous=None
    def process(self,frame,t):
        p=blob(frame,self.cfg['pivot_hsv'],self.cfg);q=blob(frame,self.cfg['tip_hsv'],self.cfg)
        result=dict(valid=False,calibrated=self.cfg['home_angle_rad'] is not None,pivot_px=p,tip_px=q,theta_down_rad=None,theta_upright_rad=None,omega_rad_s=None)
        if p is None or q is None:self.history.clear();self.previous=None;return result
        dx=q[0]-p[0];dy=q[1]-p[1];length=math.hypot(dx,dy)
        if not self.cfg['min_length_px']<=length<=self.cfg['max_length_px']:self.history.clear();self.previous=None;return result
        a=math.atan2(dx,dy) # clockwise from image-down toward image-right
        self.history.append((a,length))
        home=self.cfg['home_angle_rad'];L=self.cfg['home_length_px']
        if home is None:return result
        if L and abs(length/L-1)>self.cfg['home_length_tolerance_fraction']:self.previous=None;return result
        # MuJoCo positive rotates upright toward +x. theta_up = pi - down.
        down=wrap(a-home);up=wrap(math.pi-down);omega=None
        if self.previous is not None:
            pt,pu=self.previous;dt=t-pt
            if 0<dt<=self.cfg['max_gap_s']:omega=wrap(up-pu)/dt
        self.previous=(t,up)
        result.update(valid=True,theta_down_rad=down,theta_upright_rad=up,omega_rad_s=omega,length_px=length)
        return result
