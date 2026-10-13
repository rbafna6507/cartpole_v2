import cv2
import numpy as np

class GreenArm:
    def __init__(self,cfg):self.cfg=cfg;self.pivot=None;self.last_t=None
    def select(self,x,y):self.pivot=np.array([x,y],float);self.last_t=None
    def detect(self,frame,t):
        c=self.cfg
        if self.pivot is None:return None,None
        if self.last_t is not None and t-self.last_t>.3:
            self.pivot=None;return None,None
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,np.array(c['green_hsv'][0],np.uint8),np.array(c['green_hsv'][1],np.uint8))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        candidates=[q for q in cs if c['arm_min_area']<cv2.contourArea(q)<frame.shape[0]*frame.shape[1]*c['arm_max_area_fraction'] and cv2.pointPolygonTest(q,tuple(self.pivot),True)>-c['pivot_search_radius_px']]
        if len(candidates)!=1:return None,None
        contour=candidates[0];inside=np.zeros(mask.shape,np.uint8);cv2.drawContours(inside,[contour],-1,255,-1)
        inside=cv2.erode(inside,np.ones((7,7),np.uint8))
        roi=np.zeros(mask.shape,np.uint8);cv2.circle(roi,tuple(np.round(self.pivot).astype(int)),c['pivot_search_radius_px'],255,-1)
        dark=((hsv[:,:,2]<c['dark_max_value']) & (hsv[:,:,1]<100) & (inside>0) & (roi>0)).astype(np.uint8)*255
        ds,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        points=[]
        for q in ds:
            area=cv2.contourArea(q);per=cv2.arcLength(q,True)
            if not c['pivot_min_area']<=area<=c['pivot_max_area'] or per==0 or 4*np.pi*area/per**2<.35:continue
            m=cv2.moments(q);points.append(np.array([m['m10']/m['m00'],m['m01']/m['m00']]))
        if len(points)!=1:return None,None
        pivot=points[0]
        ys,xs=np.nonzero(inside);pts=np.column_stack((xs,ys)).astype(float)
        # Long green silhouette axis, oriented away from selected pivot.
        center=pts.mean(0);_,vec=np.linalg.eigh(np.cov(pts.T));axis=vec[:,-1]
        if np.dot(center-pivot,axis)<0:axis=-axis
        proj=(pts-pivot)@axis;length=np.percentile(proj,98)
        if length<c['min_length_px']:return None,None
        # Pivot must lie near narrow end, not on one of the round-head screws.
        if np.percentile(proj,2)<-.2*length:return None,None
        far=pts[proj>.8*length];tip=far.mean(0)
        self.pivot=pivot;self.last_t=t
        return tuple(pivot),tuple(tip)
