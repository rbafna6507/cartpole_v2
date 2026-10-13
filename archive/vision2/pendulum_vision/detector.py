"""Geometric detector for a green shaft with a wider circular weighted end.

All processing is bounded to 960px width. No pose is extrapolated. A missed
frame does not disable subsequent detection. Confidence is a heuristic quality
score, not a probability or a calibrated angular error bound.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np


@dataclass
class Pose:
    pivot: tuple
    bob: tuple
    angle: float  # atan2(image dx, image dy): zero down, positive toward right
    length: float
    confidence: float
    width_ratio: float


@dataclass
class Detection:
    pose: Pose | None
    reason: str
    mask: np.ndarray
    candidates: int = 0


class ArmDetector:
    def __init__(self, hue_low=40, hue_high=95, saturation_min=110,
                 green_min=60, chroma_min=30, processing_width=960):
        self.hue_low, self.hue_high = hue_low, hue_high
        self.saturation_min = saturation_min
        self.green_min, self.chroma_min = green_min, chroma_min
        self.processing_width = processing_width
        self.seed = None

    def select(self, x, y):
        self.seed = np.array([x, y], float)

    def detect(self, frame):
        scale = min(1., self.processing_width / frame.shape[1])
        image = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        b, g, r = [image[:, :, i].astype(np.int16) for i in range(3)]
        mask = ((hsv[:, :, 0] >= self.hue_low) & (hsv[:, :, 0] <= self.hue_high)
                & (hsv[:, :, 1] >= self.saturation_min) & (g >= self.green_min)
                & (g-r >= self.chroma_min) & (g-b >= 8)).astype(np.uint8)*255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        matches = []
        unit = image.shape[1]/960
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 300*unit**2 or area > image.shape[0]*image.shape[1]*.20:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            # Clipped silhouettes cannot supply reliable endpoint geometry.
            if x <= 0 or y <= 0 or x+w >= image.shape[1] or y+h >= image.shape[0]:
                continue
            filled = np.zeros((h+4, w+4), np.uint8)
            local = contour - np.array([[[x-2, y-2]]])
            cv2.drawContours(filled, [local], -1, 255, -1)
            yy, xx = np.nonzero(filled)
            pts = np.column_stack([xx, yy]).astype(float)
            center = pts.mean(axis=0)
            values, vectors = np.linalg.eigh(np.cov(pts.T))
            if values[1] < 4*max(values[0], 1):
                continue
            axis = vectors[:, -1]
            projection = (pts-center) @ axis
            lo, hi = np.percentile(projection, [1, 99])
            span = hi-lo
            if span < 55*unit:
                continue
            # The circular weight distinguishes the two ends without history.
            low_count = np.sum(projection < lo+.23*span)
            high_count = np.sum(projection > hi-.23*span)
            if max(low_count, high_count) < 1.15*min(low_count, high_count):
                continue
            if low_count > high_count:
                axis = -axis
                projection = -projection
                lo, hi = -hi, -lo
            # The end disks are convex. Fill rim-connected screw/weight holes for
            # endpoint localization, while retaining the original shaft for support tests.
            solid = np.zeros_like(filled)
            cv2.drawContours(solid, [cv2.convexHull(local)], -1, 255, -1)
            distance = cv2.distanceTransform(solid, cv2.DIST_L2, 5)
            grid_y, grid_x = np.indices(filled.shape)
            grid_proj = (grid_x-center[0])*axis[0] + (grid_y-center[1])*axis[1]
            distance[grid_proj < lo+.6*span] = 0
            _, radius, _, bob_i = cv2.minMaxLoc(distance)
            if radius < 5*unit:
                continue
            # Fit the exposed circular rim. A distance-transform plateau drifts
            # toward the shaft when holes or reflections interrupt the rim.
            hull_pts=cv2.convexHull(local).reshape(-1,2).astype(float)
            arc=hull_pts[((hull_pts-center)@axis)>lo+.70*span]
            if len(arc)<5:
                continue
            matrix=np.column_stack((2*arc[:,0],2*arc[:,1],np.ones(len(arc))))
            fit=np.linalg.lstsq(matrix,np.sum(arc**2,axis=1),rcond=None)[0]
            bob=fit[:2]
            radius2=float(fit[2]+bob@bob)
            if radius2<=0:
                continue
            radius=math.sqrt(radius2)
            residual=float(np.sqrt(np.mean((np.linalg.norm(arc-bob,axis=1)-radius)**2)))
            if residual>radius*.12 or not .06*span<radius<.25*span:
                continue
            offset = np.array([x-2, y-2])
            crop = image[max(0,y-2):y+h+2, max(0,x-2):x+w+2]
            if crop.shape[:2] != filled.shape:
                continue
            val = crop.max(axis=2)
            valid_green = (filled > 0) & (grid_proj < lo+.55*span) & (val > self.green_min)
            reference = np.median(val[valid_green]) if np.any(valid_green) else 0
            inside = cv2.erode(solid, np.ones((3,3), np.uint8))
            dark = ((val < reference*.70) & (inside > 0)
                    & (grid_proj < lo+.25*span)).astype(np.uint8)*255
            holes, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            pivots = []
            for hole in holes:
                a = cv2.contourArea(hole)
                per = cv2.arcLength(hole, True)
                if a < 5*unit**2 or per <= 0 or 4*math.pi*a/per**2 < .3:
                    continue
                m = cv2.moments(hole)
                p = np.array([m['m10']/m['m00'], m['m01']/m['m00']])
                transverse = abs(axis[0]*(p-center)[1]-axis[1]*(p-center)[0])
                if transverse > radius*.65 or a > math.pi*(radius*.55)**2:
                    continue
                pivots.append((a, p))
            if not pivots:
                continue
            pivots.sort(key=lambda item: item[0], reverse=True)
            if len(pivots)>1 and pivots[1][0] > .7*pivots[0][0]:
                continue
            pivot = pivots[0][1]
            vector = bob-pivot
            length = float(np.linalg.norm(vector))
            width_ratio = 2*radius/max(length,1)
            if length < 45*unit or not .12 < width_ratio < .50:
                continue
            direction = vector/length
            # Check support along the rigid shaft; disconnected green blobs cannot pass.
            support=[]
            for fraction in np.linspace(.12,.75,30):
                point=np.rint(pivot+fraction*vector).astype(int)
                support.append(filled[point[1],point[0]]>0)
            if np.mean(support) < .95:
                continue
            mid = (projection > lo+.2*span) & (projection < lo+.65*span)
            cross = (pts[mid]-pivot) @ np.array([-direction[1],direction[0]])
            shaft_width = float(np.percentile(cross,95)-np.percentile(cross,5))
            if shaft_width/length > .24 or shaft_width < 3*unit:
                continue
            quality = float(np.clip(1-shaft_width/length, 0, 1))
            p = (pivot+offset)/scale
            q = (bob+offset)/scale
            matches.append(Pose(tuple(p),tuple(q),math.atan2(vector[0],vector[1]),
                                length/scale,quality,width_ratio))
        if self.seed is not None and matches:
            nearby = [m for m in matches if np.linalg.norm(np.array(m.pivot)-self.seed) < frame.shape[1]*.15]
            matches = nearby
        if len(matches) != 1:
            return Detection(None, 'ambiguous arms' if len(matches)>1 else 'no reliable arm geometry',mask,len(matches))
        self.seed = None  # selection disambiguates acquisition, never limits later cart travel
        return Detection(matches[0], 'measured',mask,1)
