"""Passive repeat with lossless unannotated snapshots; never enables motion."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,threading,time,urllib.request
from cartpole_sdk.rig import Rig
from cartpole_sdk.identification.experiments import sample_camera_clock
from cartpole_sdk.sensing.telemetry import EncoderPublisher

OUTPUT=Path('runs/encoder-tightening-20261021/manual-map-upright-verification-04')

class PassiveCameraRecorder:
    """Record gaps for offline rejection; has no control eligibility or serial access."""
    def __init__(self,url,directory,seconds):
        self.url=url;self.directory=directory;self.seconds=seconds
        self.stop=threading.Event();self.ready=threading.Event();self.report={'url':url,'frames':0,'stream_records':0,'stale_records':0,'transport_events':[],'clock':'camera host-read proxy; passive acquisition preserves invalid frames for offline rejection'}
        self.worker=threading.Thread(target=self.run,daemon=True)
    def run(self):
        self.report['started_ns']=time.monotonic_ns();deadline=time.monotonic()+self.seconds
        try:
            self.report['clock_sync']={'method':'http-roundtrip-midpoint','start':sample_camera_clock(self.url)}
            with (self.directory/'vision.ndjson').open('xb') as target:
                while not self.stop.is_set() and time.monotonic()<deadline:
                    try:
                        with urllib.request.urlopen(self.url,timeout=2) as response:
                            while not self.stop.is_set() and time.monotonic()<deadline:
                                line=response.readline(4*1024*1024+1)
                                if not line or len(line)>4*1024*1024 or not line.endswith(b'\n'):raise ValueError('stream interrupted or oversized record')
                                row=json.loads(line);row['collector_received_ns']=time.monotonic_ns()
                                if row.get('schema')!='cartpole-sensing-stream-v1':raise ValueError('unexpected sensing schema')
                                target.write((json.dumps(row,separators=(',',':'))+'\n').encode());target.flush()
                                self.report['stream_records']+=1;v=row.get('vision',{})
                                if v.get('stale') is False and not v.get('worker_error'):
                                    self.report['frames']+=1;self.ready.set()
                                else:self.report['stale_records']+=1
                    except Exception as error:
                        self.report['transport_events'].append({'host_monotonic_ns':time.monotonic_ns(),'error':repr(error)})
                        self.stop.wait(.2)
        except Exception as error:self.report['failure']=repr(error)
        finally:
            try:self.report.setdefault('clock_sync',{})['end']=sample_camera_clock(self.url)
            except Exception as error:self.report['clock_end_error']=repr(error)
            self.report['finished_ns']=time.monotonic_ns()
            path=self.directory/'vision.ndjson'
            if path.exists():self.report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            (self.directory/'vision-report.json').write_text(json.dumps(self.report,indent=2)+'\n')
    def start(self):
        self.worker.start()
        if not self.ready.wait(5):raise RuntimeError('camera did not provide fresh initial frame')
        self.check()
    def check(self):
        if not self.worker.is_alive():raise RuntimeError('passive camera worker stopped')
    def close(self):
        self.stop.set();self.worker.join(5)
        if self.worker.is_alive():self.report['failure']='passive camera worker did not close'
        return self.report

def snapshots(directory,stop,ready,result):
    directory.mkdir()
    base='http://127.0.0.1:3090'
    result.update(frames=0,failures=0,clock='Jetson monotonic HTTP request bounds; not exposure timestamps',format='lossless unannotated PNG',requested_hz=2)
    def read(url):
        with urllib.request.urlopen(url,timeout=2) as response:return response.read()
    with (directory/'frames.ndjson').open('w') as log:
        while not stop.is_set():
            began=time.monotonic();row={'request_start_ns':time.monotonic_ns()}
            try:
                before=json.loads(read(base+'/api/state?measurement=1'))
                raw=read(base+'/snapshot.png')
                after=json.loads(read(base+'/api/state?measurement=1'))
                if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('snapshot is not a PNG')
                name=f'{result["frames"]:06d}.png';(directory/name).write_bytes(raw)
                row.update(file=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),request_end_ns=time.monotonic_ns(),state_before=before,state_after=after)
                result['frames']+=1;ready.set()
            except Exception as error:row['error']=repr(error);result['failures']+=1
            log.write(json.dumps(row,separators=(',',':'))+'\n');log.flush()
            stop.wait(max(0.,.5-(time.monotonic()-began)))

def main():
    p=OUTPUT;p.mkdir(exist_ok=False,parents=True)
    camera=PassiveCameraRecorder('http://127.0.0.1:3090/api/sensing-stream?max_hz=100',p,330.)
    report={'purpose':'repeat slow manual rotations with raw snapshots; no powered motion or calibration writes','samples':[],'snapshots':{},'collector_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    stop=threading.Event();ready=threading.Event();worker=None
    try:
        camera.start()
        with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=p,vision_publisher=EncoderPublisher(3096)) as rig:
            try:
                report['before']=asdict(rig._stopped_healthy());report['info_before']=asdict(rig.get_info())
                if report['info_before']['encoder_upright_raw']!=533:raise RuntimeError('upright reference differs from expected 533')
                worker=threading.Thread(target=snapshots,args=(p/'images',stop,ready,report['snapshots']),daemon=True);worker.start()
                if not ready.wait(6):raise RuntimeError('raw snapshot recording did not become ready')
                print('PASSIVE RECORDING READY: motor disabled; encoder, vision, and lossless images recording',flush=True)
                deadline=time.monotonic()+180
                while time.monotonic()<deadline and not (p/'finish').exists():
                    rig._require();rig._fresh(rig.state);camera.check();s=rig.state
                    if s.enabled or s.mode or not s.healthy or s.fault:raise RuntimeError('not healthy disabled')
                    if not worker.is_alive():raise RuntimeError('snapshot worker stopped')
                    report['samples'].append({'host_monotonic_ns':time.monotonic_ns(),'state':asdict(s),'info':asdict(rig.get_info())})
                    time.sleep(.25)
                report['finish_reason']='operator_done' if (p/'finish').exists() else 'time_limit'
            finally:
                rig.stop();report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
    except BaseException as error:report['error']=repr(error)
    finally:
        stop.set()
        if worker:worker.join(8)
        report['camera']=camera.close();(p/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'directory':str(p),'error':report.get('error'),'info_samples':len(report['samples']),'after':report.get('after'),'info_after':report.get('info_after'),'snapshots':report['snapshots'],'camera_frames':report['camera'].get('frames')}),flush=True)
    return int('error' in report)

if __name__=='__main__':raise SystemExit(main())
