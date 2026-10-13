import unittest,tempfile,json,csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab import Recorder,run_drive,DEFAULT_CONFIG
from analysis import FIELDS
class FakeDrive:
 def __init__(self):self.lines=[];self.commands=[];self.seq=0;self.x=0;self.active=False
 def write(self,b):
  s=b.decode().strip();self.commands.append(s)
  if s=='INFO':self.lines.append(b'I protocol=3 board=fake\n')
  elif s=='STREAM':self.active=True;self.event('STREAM')
  elif s.startswith('LIMITS'):self.event('LIMITS')
  elif s.startswith('HOME'):self.event('HOME')
  elif s.startswith('MOVE'):
   _,i,x=s.split();self.x=float(x)/1000;self.event('MOVE_ACCEPT '+i+' '+x);self.event('MOVE_DONE '+i)
  elif s=='STOP':
   if self.active:self.event('END host_stop 0 0 0')
   self.active=False
  return len(b)
 def event(self,s):self.lines.append(f'E {1000000+self.seq*1000} {s}\n'.encode())
 def readline(self):
  if self.lines:return self.lines.pop(0)
  if self.active:
   i=self.seq;self.seq+=1
   vals=[i,1000000+i*1000,1000,1000,1000,1.5,0,32,90,2000,0,0,0,100,1,1,round(self.x*26666.6667),self.x,0,0,1,0,1,1]
   return ('D '+','.join(map(str,vals))+'\n').encode()
  return b''
 def close(self):pass
class DriveTest(unittest.TestCase):
 def test_guided_round_trip_saved(self):
  with tempfile.TemporaryDirectory() as td:
   serial=FakeDrive();rec=Recorder(None,serial_instance=serial)
   args=SimpleNamespace(speed=30,accel=300,jerk=3000,distance=20,repeats=1,single=False,config=str(DEFAULT_CONFIG),note='test')
   clock=[10.]
   def now():clock[0]+=.001;return clock[0]
   replies=['','300','','MOVE','0']
   with patch('builtins.input',side_effect=replies),patch('lab.time.monotonic',side_effect=now):run_drive(rec,args,Path(td))
   moves=[s for s in serial.commands if s.startswith('MOVE')]
   self.assertEqual(moves,['MOVE 1 20','MOVE 2 0','MOVE 3 -20','MOVE 4 0'])
   report=json.loads((Path(td)/'drive_report.json').read_text());self.assertTrue(report['completed'])
   cap=json.loads((Path(td)/'drive_capture.json').read_text())
   self.assertTrue(any(s['command']=='HOME 300.0' for s in cap['host_commands']))
   self.assertGreater(cap['rows'],100)
if __name__=='__main__':unittest.main()
