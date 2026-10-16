from pathlib import Path
import importlib.util, sys, json, time, statistics, dataclasses, hashlib, tempfile
import cv2, numpy as np
evidence=Path(__file__).resolve().parent
root=evidence.parents[2]
base_path=evidence/'contour-prefilter-baseline.py'
scratch=tempfile.TemporaryDirectory(prefix='cartpole-detector-replay-')
candidate_path=Path(scratch.name)/'candidate.py'
old='''        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 300*unit**2 or area > image.shape[0]*image.shape[1]*.20:
'''
new='''        min_area = 300*unit**2
        max_area = image.shape[0]*image.shape[1]*.20
        for contour in contours:
            # Fewer than three points have exactly zero polygon area.
            if len(contour) < 3:
                continue
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
'''
source=base_path.read_text(); assert source.count(old)==1
candidate_path.write_text(source.replace(old,new))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
base=load('detector_baseline',base_path);candidate=load('detector_candidate',candidate_path)
cv2.setNumThreads(2)
b=base.ArmDetector(processing_width=640);c=candidate.ArmDetector(processing_width=640)
def fields(r):
    return (dataclasses.asdict(r.pose) if r.pose else None,r.reason,r.candidates)
def compare(frame,label):
    a=b.detect(frame); z=c.detect(frame)
    assert fields(a)==fields(z),(label,fields(a),fields(z))
    assert np.array_equal(a.mask,z.mask),label
    return bool(a.pose)
def measure(frame, timings, idx):
    order=[('baseline',b),('candidate',c)]
    if idx%2:order.reverse()
    for name,detector in order:
        start=time.perf_counter_ns();detector.detect(frame);timings[name].append((time.perf_counter_ns()-start)/1e6)
def summary(t):
    return {name:{'count':len(v),'mean_ms':statistics.mean(v),'median_ms':statistics.median(v),'p95_ms':float(np.percentile(v,95))} for name,v in t.items()}
stills=[evidence/'quality/current-auto-frame.png',evidence/'raw-80fps-snapshot.png',*sorted((root/'tests/vision_runtime/fixtures').glob('*.png'))]
still_result=[]
for p in stills:
    frame=cv2.imread(str(p));assert frame is not None
    result=compare(frame,p.name)
    for i in range(15):b.detect(frame);c.detect(frame)
    t={'baseline':[],'candidate':[]}
    for i in range(200):measure(frame,t,i)
    scale=min(1,640/frame.shape[1]);img=cv2.resize(frame,None,fx=scale,fy=scale) if scale<1 else frame
    mask,_=b.segment(img);contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    still_result.append({'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'detected':result,'exact_fields_and_mask':True,'contours':len(contours),'contours_lt3':sum(len(v)<3 for v in contours),'timing':summary(t)})
# The historical moving recording remains in the adjacent original project.
# An explicit input path can be supplied without copying or editing it.
movie=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'cartpole/vision/evidence/live-motion/raw.avi'
passes=[]
for run in range(3):
    cap=cv2.VideoCapture(str(movie));assert cap.isOpened();t={'baseline':[],'candidate':[]};n=detected=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        if run==0:detected+=compare(frame,f'motion-{n}')
        measure(frame,t,n+run);n+=1
    cap.release();passes.append({'run':run,'frames':n,'detected':detected if run==0 else None,'timing':summary(t)})
    print('pass',run,n,summary(t),flush=True)
report={'candidate':'skip contour lengths below three (exactly zero polygon area), hoist unchanged area thresholds','opencv':cv2.__version__,'opencv_threads':cv2.getNumThreads(),'width':640,'stills':still_result,'motion':{'source':str(movie),'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),'exact_fields_and_mask_all_frames':True,'passes':passes},'limitations':['60-frame current burst retained pose rows and first/last raw frames only; full burst cannot be reprocessed.','Timings are local workstation only; not a live Jetson throughput claim.']}
# Keep the archived measurement immutable; print a fresh report to stdout.
print(json.dumps(report,indent=2))
scratch.cleanup()
