import unittest,tempfile,csv,sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis import FIELDS,stationary,analyze,ode,angle_from_raw,load_csv,export_model,write_json
from lab import Recorder

def datafile(path,t,phi,zero=4000):
    raw=np.mod(np.rint(zero+np.asarray(phi)*4096/(2*np.pi)),4096)
    with open(path,'w',newline='') as f:
        w=csv.writer(f);w.writerow(FIELDS)
        for i,(ts,r) in enumerate(zip(t,raw)):
            w.writerow([i,int(ts*1e6),2000,int(r),int(r),r*2*np.pi/4096,0,32,90,2000,0,0,0,150,1,1,0,0,0,0,0,0,0,0])

class AnalysisTests(unittest.TestCase):
    def test_raw_wrap_noise(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'noise.csv';t=np.arange(0,3,.002)
            datafile(p,t,.001*np.sin(t*11),zero=4095)
            result=stationary(p)
            self.assertLess(result['angle_peak_to_peak_deg'],.3)
            self.assertEqual(result['quality']['magnet_not_detected'],0)
    def test_timestamp_reset_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.csv';t=np.r_[np.arange(30)*.002,np.arange(30)*.002];datafile(p,t,np.zeros(len(t)))
            with self.assertRaisesRegex(ValueError,'timestamps'):load_csv(p)
    def test_mapping_no_extrapolation_and_sign(self):
        cal=dict(zero_raw=4000,nodes_raw_delta_angle_rad=[[-1024,np.pi/2],[0,0],[1024,-np.pi/2]])
        a=angle_from_raw(np.array([0]),4000,cal)
        self.assertLess(a[0],0)
        with self.assertRaisesRegex(ValueError,'outside'):angle_from_raw(np.array([1800]),4000,cal)
    def test_release_required(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'swing.csv';t=np.arange(0,8,.002);datafile(p,t,.3*np.cos(9*t)*np.exp(-t*.1))
            with self.assertRaisesRegex(ValueError,'release'):analyze(p)
    def test_gaps_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'gap.csv';t=np.r_[np.arange(0,3,.002),np.arange(3.1,8,.002)];datafile(p,t,.3*np.cos(9*t))
            with self.assertRaisesRegex(ValueError,'gap'):analyze(p,release_s=0,zero_raw=4000)
    def test_period_fit_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'swing.csv';t=np.arange(0,9,.002)
            y=ode(t,[9.,.18,.7,0],.5,0)
            rng=np.random.default_rng(1);datafile(p,t,y+rng.normal(0,.0003,len(t)))
            m=analyze(p,release_s=0,zero_raw=4000,fit=True)
            self.assertAlmostEqual(m['small_angle_period_estimate_s'],2*np.pi/9,delta=.015)
            self.assertNotIn('fit_error',m);f=m['dynamics_fit']
            self.assertAlmostEqual(f['w0_rad_s'],9,delta=.05)
            self.assertAlmostEqual(f['beta_per_s'],.18,delta=.05)
            self.assertAlmostEqual(f['gamma_rad_s2'],.7,delta=.12)
            self.assertLess(f['fit_rms_deg'],.2)
            out=Path(td)/'model.json';export_model(m,.02275,.075,out)
            model=json.loads(out.read_text());self.assertGreater(model['I_pivot'],model['mass']*model['com_dist']**2)
    def test_invalid_rows_preserved_as_quality(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'noise.csv';t=np.arange(0,2,.002);datafile(p,t,np.zeros(len(t)))
            with p.open() as f:rows=list(csv.reader(f))
            rows[15][3]='-1';rows[15][14]='0'
            with p.open('w',newline='') as f:csv.writer(f).writerows(rows)
            result=stationary(p);self.assertEqual(result['quality']['invalid_samples'],1)

class FakeSerial:
    def __init__(self):self.lines=[];self.commands=[]
    def write(self,b):
        c=b.decode().strip();self.commands.append(c)
        if c=='INFO':self.lines.append(b'I protocol=3 board=fake\n')
        elif c=='ARM':
            self.lines += [b'E 1000000 ARMED\n',b'E 1000000 HELD_release_now\n']
            for i in range(200):
                if i==20:self.lines.append(b'E 1040000 RELEASE_auto\n')
                self.lines.append(('D '+','.join(map(str,[i,1000000+i*2000,2000,1000,1000,1.5,0,32,90,2000,0,0,0,100,1,1,0,0,0,0,0,0,0,0]))+'\n').encode())
            self.lines.append(b'E 1400000 END quiet 0 0 0\n')
        return len(b)
    def readline(self):return self.lines.pop(0) if self.lines else b''
    def close(self):pass

class CaptureTests(unittest.TestCase):
    def test_release_metadata_and_stop(self):
        with tempfile.TemporaryDirectory() as td:
            ser=FakeSerial();rec=Recorder(None,serial_instance=ser)
            path,cap=rec.collect(Path(td)/'run',command='ARM',duration=None)
            self.assertEqual(cap['rows'],200);self.assertAlmostEqual(cap['release_s'],.04)
            self.assertIn('STOP',ser.commands)
            with path.open() as f:self.assertEqual(len(list(csv.reader(f))),201)
            self.assertTrue(path.with_name('run_protocol.log').exists())

if __name__=='__main__':unittest.main()
