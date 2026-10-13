"""Two-point, affine rail calibration using the rigid cart pivot. Units mm."""
from collections import deque
import numpy as np

class CartPosition:
    def __init__(self):
        self.motion=deque(maxlen=12);self.samples=deque(maxlen=20);self.a=None;self.b=None;self.span=None;self.previous=None;self.last_t=None
    def observe(self,p,t):
        if self.last_t is not None and t-self.last_t>.1:self.samples.clear();self.previous=None
        self.last_t=t
        result=dict(cart_valid=False,cart_x_mm=None,cart_x_m=None,cart_v_mm_s=None,cart_a_mm_s2=None,cart_v_m_s=None,cart_a_m_s2=None,derivative_window_s=None,cart_cross_track_px=None)
        if p is None:self.samples.clear();self.previous=None;return result
        p=np.asarray(p,float);self.samples.append(p)
        if self.a is None or self.b is None:return result
        direction=self.b-self.a;norm2=float(direction@direction);f=float((p-self.a)@direction/norm2)
        cross=float(np.linalg.norm(p-(self.a+f*direction)));result['cart_cross_track_px']=cross
        # This POC only reports within calibrated extent and near the rail line.
        if not 0<=f<=1 or cross>max(5.,np.sqrt(norm2)*.02):self.previous=None;return result
        x=(f-.5)*self.span
        if self.previous is None:self.motion.clear()
        self.motion.append((t,x))
        while len(self.motion)>1 and t-self.motion[0][0]>.15:self.motion.popleft()
        v=acc=window=None
        if len(self.motion)>=5:
            data=np.asarray(self.motion);dt=data[:,0]-t;window=float(-dt[0])
            if window>=.025:
                coeff=np.polynomial.polynomial.polyfit(dt,data[:,1],2)
                v=float(coeff[1]);acc=float(2*coeff[2])
        self.previous=(t,x)
        result.update(cart_valid=True,cart_x_mm=x,cart_x_m=x/1000,
                      cart_v_mm_s=v,cart_a_mm_s2=acc,
                      cart_v_m_s=None if v is None else v/1000,
                      cart_a_m_s2=None if acc is None else acc/1000,
                      derivative_window_s=window)
        return result
    def mark(self,which,span=None):
        if len(self.samples)<20:raise ValueError('Hold cart still with pivot visible for at least 20 frames')
        pts=np.array(self.samples);center=np.median(pts,axis=0)
        if np.max(np.linalg.norm(pts-center,axis=1))>2:raise ValueError('Cart is moving or detection jitter exceeds 2 pixels')
        if which=='a':self.a=center;self.b=None;self.span=None
        elif which=='b':
            if self.a is None:raise ValueError('Record left reference A first')
            if span is None or not np.isfinite(span) or not 10<=span<=1000:raise ValueError('Enter measured separation in mm (10–1000)')
            if np.linalg.norm(center-self.a)<30:raise ValueError('References too close in image; need at least 30 pixels')
            self.b=center;self.span=float(span)
        else:raise ValueError('Unknown reference')
        self.previous=None
        return self.as_dict()
    def as_dict(self):return dict(a_px=None if self.a is None else self.a.tolist(),b_px=None if self.b is None else self.b.tolist(),span_mm=self.span,zero='midpoint',positive='A to B')
