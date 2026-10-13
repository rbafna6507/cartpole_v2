import json,sys
from pathlib import Path
import cv2,numpy as np
from green_arm import GreenArm
cfg=json.loads(Path(sys.argv[1]).read_text())
def scene(extra):
    f=np.full((600,960,3),180,np.uint8)
    cv2.rectangle(f,(470,180),(495,410),(0,180,0),-1)
    cv2.circle(f,(482,194),6,(40,10,5),-1)
    # Two nearby green objects enter the search circle but aren't the arm.
    if extra>0:cv2.rectangle(f,(425,155),(450,195),(0,180,0),-1)
    if extra>1:cv2.rectangle(f,(513,180),(545,215),(0,180,0),-1)
    return f
for count in (0,1,2):
    d=GreenArm(cfg);d.select(482,194)
    p,q=d.detect(scene(count),0)
    assert p is not None and np.linalg.norm(np.array(p)-[482,194])<2,d.reason
    assert q[1]>350
    print(count+1,'green regions: correct pivot')
d=GreenArm(cfg);d.select(482,194)
assert d.detect(np.zeros((600,960,3),np.uint8),0)==(None,None)
print('Blank frame rejected')
f=scene(2)
for y in (215,236):cv2.circle(f,(482,y),6,(40,10,5),-1)
d=GreenArm(cfg);d.select(482,194);p,q=d.detect(f,0)
assert p is not None and abs(p[1]-194)<2,d.reason
print('Three dark candidates: selected correct screw')
d=GreenArm(cfg);d.select(482,204.5)
assert d.detect(f,0)==(None,None)
assert 'Ambiguous' in d.reason
print('Equally close pivots rejected')
