"""Click-seeded green arm tracker; discriminate nearby green objects geometrically."""
import cv2
import numpy as np

class GreenArm:
    def __init__(self,cfg):
        self.cfg=cfg;self.pivot=None;self.last_t=None
        self.reason="Click pivot screw"
    def select(self,x,y):
        self.pivot=np.array([x,y],float);self.last_t=None
    def detect(self,frame,t):
        c=dict(self.cfg);scale=frame.shape[1]/960.0
        for k in ['pivot_search_radius_px','min_length_px']:
            c[k]=max(1,round(c[k]*scale))
        for k in ['arm_min_area','pivot_min_area','pivot_max_area']:
            c[k]*=scale*scale
        if self.pivot is None:
            self.reason='Click pivot screw';return None,None
        if self.last_t is not None and t-self.last_t>.3:
            self.pivot=None;self.reason='Tracking gap: click pivot again';return None,None
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,np.array(c['green_hsv'][0],np.uint8),np.array(c['green_hsv'][1],np.uint8))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        candidates=[q for q in contours if c['arm_min_area']<cv2.contourArea(q)<frame.shape[0]*frame.shape[1]*c['arm_max_area_fraction'] and cv2.pointPolygonTest(q,tuple(self.pivot),True)>-c['pivot_search_radius_px']]
        roi=np.zeros(mask.shape,np.uint8)
        cv2.circle(roi,tuple(np.round(self.pivot).astype(int)),c['pivot_search_radius_px'],255,-1)
        matches=[];dark_count=0
        for contour in candidates:
            inside=np.zeros(mask.shape,np.uint8)
            cv2.drawContours(inside,[contour],-1,255,-1)
            inside=cv2.erode(inside,np.ones((7,7),np.uint8))
            dark=((hsv[:,:,2]<c['dark_max_value']) & (inside>0) & (roi>0)).astype(np.uint8)*255
            holes,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            ys,xs=np.nonzero(inside);pts=np.column_stack((xs,ys)).astype(float)
            if len(pts)<3:continue
            center=pts.mean(0);values,vectors=np.linalg.eigh(np.cov(pts.T))
            # Brackets/blobs are not long pendulum arms.
            if values[-1]<3*max(values[0],1):continue
            for hole in holes:
                area=cv2.contourArea(hole);per=cv2.arcLength(hole,True)
                if not c['pivot_min_area']<=area<=c['pivot_max_area'] or per==0 or 4*np.pi*area/per**2<.35:continue
                dark_count+=1
                m=cv2.moments(hole)
                pivot=np.array([m['m10']/m['m00'],m['m01']/m['m00']])
                distance=float(np.linalg.norm(pivot-self.pivot))
                if distance>c['pivot_search_radius_px']:continue
                axis=vectors[:,-1].copy()
                if np.dot(center-pivot,axis)<0:axis=-axis
                proj=(pts-pivot)@axis;length=np.percentile(proj,98)
                if length<c['min_length_px'] or np.percentile(proj,2)<-.2*length:continue
                tip=pts[proj>.8*length].mean(0)
                matches.append((distance,pivot,tip))
        if not matches:
            self.reason=f'No arm/pivot match: {len(candidates)} green, {dark_count} dark; click screw'
            return None,None
        matches.sort(key=lambda m:m[0])
        # Do not guess when two plausible pivots are almost equally close.
        if len(matches)>1 and matches[1][0]-matches[0][0]<8*scale:
            self.reason='Ambiguous pivots: click closer to screw center';return None,None
        _,pivot,tip=matches[0]
        self.pivot=pivot;self.last_t=t
        self.reason=f'Arm and pivot detected ({len(candidates)} green regions)'
        return tuple(pivot),tuple(tip)
