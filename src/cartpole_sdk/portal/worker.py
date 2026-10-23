"""Trusted outbound pull worker. Uploaded modules are never imported here."""
import argparse
import base64
from dataclasses import asdict, replace
import hashlib
import math
import os
from pathlib import Path
import tempfile
import time
import http.client
import queue as thread_queue
import socket
import threading
from urllib.parse import urlsplit
from cartpole_sdk.contracts import ActionRequest, Channel, Observation, SelectionError, select_channels
from cartpole_sdk.recording import canonical_json, strict_json_loads
from .queue import Store, QueueError
from .run_recording import RunRecorder, MAX_BUNDLE_BYTES
from .budget import execution_wall_seconds
from .sandbox import Sandbox, SandboxError, validate_acceleration_ceiling

class WorkerError(ValueError):pass

class RemoteQueue:
    def __init__(self,url,token,*,timeout=1):
        parts=urlsplit(url)
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/') or parts.scheme not in ('http','https'):
            raise WorkerError('invalid portal origin')
        if parts.scheme=='http' and parts.hostname not in ('localhost','127.0.0.1','::1'):
            raise WorkerError('remote portal requires HTTPS')
        if parts.hostname is None or type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
            raise WorkerError('invalid portal timeout/origin')
        self.url=url.rstrip('/');self.parts=parts;self.token=token;self.timeout=timeout
        self._slots=threading.BoundedSemaphore(2)
    def _request(self,path,body=None,*,binary=None,lease=None):
        if not path.startswith('/api/') or '?' in path or '#' in path:
            raise WorkerError('invalid portal API path')
        data=binary if binary is not None else (None if body is None else canonical_json(body).encode())
        request_timeout=30 if binary is not None else self.timeout
        if not self._slots.acquire(blocking=False):raise WorkerError('portal request already pending')
        deadline=time.monotonic()+request_timeout
        replies=thread_queue.Queue(maxsize=1);cancel=threading.Event();state={}
        def request():
            connection=None
            try:
                kind=http.client.HTTPSConnection if self.parts.scheme=='https' else http.client.HTTPConnection
                connection=kind(self.parts.hostname,self.parts.port,timeout=request_timeout)
                state['connection']=connection
                connection.connect()
                state['socket']=connection.sock
                if cancel.is_set():raise WorkerError('portal deadline exceeded')
                connection.request('GET' if data is None else 'POST',path,body=data,
                    headers={'Authorization':'Bearer '+self.token,**({'Content-Type':'application/zip','X-Worker-Lease':lease} if binary is not None else ({'Content-Type':'application/json'} if data is not None else {}))})
                response=connection.getresponse()
                if not 200<=response.status<300:raise WorkerError('portal status rejected')
                # Fixed API endpoints never need redirects. HTTPConnection does not
                # follow them or forward a bearer token to another origin.
                length=response.getheader('Content-Length')
                if response.getheader('Transfer-Encoding') is not None or length is None or not length.isdecimal() or not 0<=int(length)<=100000:
                    raise WorkerError('invalid portal response framing')
                raw=bytearray()
                while len(raw)<int(length):
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or cancel.is_set():raise WorkerError('portal deadline exceeded')
                    state['socket'].settimeout(remaining)
                    chunk=response.read1(min(4096,int(length)-len(raw)))
                    if not chunk:raise WorkerError('incomplete portal response')
                    raw.extend(chunk)
                value=strict_json_loads(raw.decode())
                if not cancel.is_set():replies.put_nowait((value,None))
            except Exception:
                if not cancel.is_set():replies.put_nowait((None,WorkerError('portal request failed')))
            finally:
                if connection is not None:connection.close()
                self._slots.release()
        thread=threading.Thread(target=request,daemon=True)
        thread.start()
        try:
            value,error=replies.get(timeout=max(.000001,deadline-time.monotonic()))
        except thread_queue.Empty:
            cancel.set()
            connection_socket=state.get('socket')
            if connection_socket is not None:
                try:connection_socket.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            raise WorkerError('portal absolute request deadline exceeded')
        if error is not None:raise error
        return value
    def put_recording(self,identifier,worker,token,bundle):
        if not 1<=len(bundle)<=MAX_BUNDLE_BYTES:raise WorkerError('recording too large')
        return self._request('/api/jobs/'+identifier+'/recording',binary=bundle,lease=token)
    def claim(self,worker,rig,*,sensor_source=None):return self._request('/api/claim',{'rig':rig,'sensor_source':sensor_source})['job']
    def fetch(self,job,worker):
        value=self._request('/api/jobs/'+job['id']+'/artifact')
        try:source=base64.b64decode(value['source_base64'],validate=True)
        except (KeyError,ValueError) as exc:raise WorkerError('invalid artifact response') from exc
        if len(source)>65536 or value['sha256']!=job['artifact'] or hashlib.sha256(source).hexdigest()!=job['artifact']:raise WorkerError('artifact digest mismatch')
        return source
    def start(self,identifier,worker,token):return self._request('/api/jobs/'+identifier+'/start',{'lease':token})
    def heartbeat(self,identifier,worker,token):return self._request('/api/jobs/'+identifier+'/heartbeat',{'lease':token})
    def finish(self,identifier,worker,token,status,result):return self._request('/api/jobs/'+identifier+'/finish',{'lease':token,'status':status,'result':result})

class SimulationBridge:
    kind='simulation'
    def prepare(self,duration,identifier):
        from cartpole_sdk.sim import SimulationConfig
        from cartpole_sdk.sim.executor import ExecutorSimulation
        self.backend=ExecutorSimulation(SimulationConfig(control_steps=10,max_steps=math.ceil(duration*100)+1))
        self.backend.reset(session_id=identifier)
        self.current=self.backend.control_observation()
        self.session=self.backend.session
        self.channels=tuple(Channel(entity,quantity,'simulation','sim:upright+x') for entity,quantity in (
            ('cart','position'),('cart','velocity'),('pole','angle'),('pole','angular_velocity')))
        self.duration_ns=int(duration*1e9)
        self.config=asdict(self.backend.config)
        return self.selected()
    def selected(self):
        # Validate required control channels while preserving every available
        # raw/processed channel and its original provenance for policy authors.
        select_channels(self.current,self.channels,now_ns=self.current.available_ns,max_age_ns=20_000_000)
        return self.current
    def arm(self,duration):pass  # simulation has no devices or physical arming
    def advance(self,value,sequence):
        observation=self.current
        request=None if value is None else ActionRequest(observation.session_id,observation.clock_id,sequence,
            observation.sequence,observation.available_ns,observation.available_ns+20_000_000,value)
        self.backend.step(request)
        self.current=self.backend.control_observation()
        if self.backend.terminated:raise WorkerError('simulation executor fault')
        return self.selected()
    def complete(self):return self.current.available_ns>=self.duration_ns
    def stop(self):
        if hasattr(self,'backend'):self.backend.close()
        return True
    def close(self):self.stop()
    def diagnostics(self):return {'sim_config':self.config,'simulation_time_ns':self.current.available_ns,
                                 'simulation_fault':self.backend.fault_reason,
                                 'action_semantics':self.backend.action_semantics,
                                 'executor':asdict(self.backend.diagnostics),'ground_truth':asdict(self.backend.ground_truth),
                                 'physical_acceptance':False}

class HardwareBridge:
    kind='magnetic-step'
    def __init__(self,port=None,*,rate_hz=100,log_dir=None,rig=None):
        self.rig=rig;self.port=port;self.rate_hz=rate_hz;self.log_dir=log_dir;self._owns=rig is None
    def prepare(self,duration,identifier):
        if self.rig is None:
            from cartpole_sdk.rig import Rig
            self.rig=Rig(self.port,rate_hz=self.rate_hz,log_dir=self.log_dir).connect()
        state=self.rig.state
        if self.rig.rate_hz==0 or self.rig.error is not None or state.enabled or state.mode!=0 or not state.homed or not state.healthy or not state.switch_profile:
            raise WorkerError('hardware queue requires operator-prepared homed healthy switch-enabled stopped rig')
        self.session=self.rig.session
        self.channels=tuple(Channel(entity,quantity,source,frame) for entity,quantity,source,frame in (
            ('cart','position','step','cart-step-home'),('cart','velocity','step','cart-step-home'),
            ('pole','angle','magnetic','encoder-zero'),('pole','angular_velocity','magnetic','encoder-zero')))
        self.current=self.rig.control_observation()
        return self.selected()
    def selected(self):
        # Validate required control channels while preserving every available
        # raw/processed channel and its original provenance for policy authors.
        select_channels(self.current,self.channels,now_ns=self.current.available_ns,max_age_ns=20_000_000)
        return self.current
    def arm(self,duration):
        self.rig.arm(duration)
        self.current=self.rig.control_observation()
        self.end=self.rig._deadline_ns/1e9-min(.01,duration*.25)
    def advance(self,value,sequence):
        observation=self.current
        request=None if value is None else ActionRequest(observation.session_id,observation.clock_id,sequence,
            observation.sequence,observation.available_ns,observation.available_ns+20_000_000,value)
        self.rig.step(request)
        remaining=self.end-time.monotonic()
        if remaining>0:
            try:self.rig.wait_state(after_tick=observation.sequence,timeout=min(.02,remaining))
            except TimeoutError:
                if time.monotonic()<self.end:raise
        self.current=self.rig.control_observation()
        return self.selected()
    def complete(self):return time.monotonic()>=self.end
    def stop(self):
        if self.rig is None:return True
        self.rig.stop();return not self.rig.state.enabled
    def close(self):
        if self._owns and self.rig is not None:self.rig.close()
    def diagnostics(self):
        state=self.rig.state
        info=getattr(self.rig,'_info',None)
        limits=getattr(self.rig,'action_limits',None)
        return {'board_state':asdict(state),'cached_board_info':None if info is None else asdict(info),
                'action_limits':None if limits is None else asdict(limits),
                'parameters_snapshot':'unavailable; no extra serial queries during worker run',
                'last_accepted_action':state.last_seq,'board_tick':state.unwrapped_tick,
                'board_time_us':state.unwrapped_us,'physical_acceptance':False}

def run_once(queue,worker,rig_id,*,bridge_factory=SimulationBridge,sandbox_factory=Sandbox,sensor_source='simulation',spool_root=None,max_acceleration=None,recording_root=None,sensing_url=None):
    """Claim one job, acknowledge child reset, then explicitly start a bounded run.

    Injection points are trusted integration/test configuration, never HTTP input.
    The production CLI always uses Sandbox. Failure never selects a host fallback.
    """
    # This value is trusted worker configuration, never a submitted job field.
    if max_acceleration is None:
        max_acceleration=25. if sensor_source=='simulation' else .25
    try:approved_ceiling=validate_acceleration_ceiling(max_acceleration)
    except SandboxError as exc:raise WorkerError(str(exc)) from exc
    job=queue.claim(worker,rig_id,sensor_source=sensor_source)
    if job is None:return None
    lease=job['lease'];identifier=job['id'];bridge=None
    status='failed';error=None;stopped=True;latencies=[];actions=0;observations=0;diagnostics={};peak_demand=0.;wall_budget=None
    began=time.monotonic();interrupted=False;recorder=None
    recording_root=recording_root or (queue.root/'recording-spool' if isinstance(queue,Store) else 'runs/portal-recordings')
    try:
        recorder=RunRecorder(recording_root,job)
        recorder.emit('attempt',backend=sensor_source,max_acceleration_m_s2=approved_ceiling)
        if sensing_url is not None:recorder.start_sensing(sensing_url,job['duration']+5)
        stopped=False  # backend factory may acquire hardware even if it raises
        bridge=bridge_factory()
        if bridge.kind!=job['source'] or bridge.kind!=sensor_source:
            raise WorkerError('worker source selection mismatch')
        wall_budget=execution_wall_seconds(bridge.kind,job['duration'])
        current=bridge.prepare(job['duration'],identifier)
        recorder.emit('session',session=asdict(bridge.session))
        recorder.observation(current)
        recorder.emit('backend_start',diagnostics=bridge.diagnostics())
        source=queue.artifact(job['artifact']) if isinstance(queue,Store) else queue.fetch(job,worker)
        if len(source)>65536 or hashlib.sha256(source).hexdigest()!=job['artifact']:raise WorkerError('artifact digest mismatch')
        with tempfile.TemporaryDirectory(prefix='cartpole-policy-',dir=spool_root) as spool:
            path=Path(spool)/'source.py';path.write_bytes(source);path.chmod(0o400)
            with sandbox_factory(path,wall_seconds=wall_budget,max_acceleration=approved_ceiling).launch() as child:
                child.reset(bridge.session)  # no physical arm before strict reset ACK
                start_began=time.monotonic()
                original_duration=job['duration']
                job=queue.start(identifier,worker,lease)
                if time.monotonic()-start_began>.25:
                    raise WorkerError('start authority response too old')
                # A successful but delayed start response is not current authority.
                # Revalidate the actual lease after setup, immediately before ARM.
                authority_began=time.monotonic()
                job=queue.heartbeat(identifier,worker,lease)
                if time.monotonic()-authority_began>.25:
                    raise WorkerError('final lease authority response too old')
                if job['id']!=identifier or job['worker']!=worker or job['rig']!=rig_id or job['lease']!=lease or job['status']!='running':
                    raise WorkerError('worker lease identity mismatch')
                if job['cancel_requested']:raise WorkerError('job cancelled')
                remaining_duration=original_duration-(time.monotonic()-start_began)
                if remaining_duration<.001:raise WorkerError('start reply exhausted motion budget')
                bridge.arm(remaining_duration)
                if isinstance(bridge,HardwareBridge):current=bridge.selected()
                wall_end=start_began+wall_budget+min(.5,job['duration'])
                heartbeat_at=time.monotonic()+.25
                sequence=0
                while not bridge.complete():
                    if time.monotonic()>=wall_end:raise WorkerError('run wall deadline exceeded')
                    if time.monotonic()>=heartbeat_at:
                        job=queue.heartbeat(identifier,worker,lease)
                        if job['cancel_requested']:status='cancelled';break
                        heartbeat_at=time.monotonic()+.25
                    action_began=time.monotonic()
                    recorder.emit('policy_call',observation_sequence=current.sequence)
                    value=child.act(current)
                    latencies.append(time.monotonic()-action_began)
                    if value is not None:
                        if type(value) not in (int,float) or abs(value)>approved_ceiling or not math.isfinite(value):raise SandboxError('policy acceleration exceeds trusted worker ceiling')
                        peak_demand=max(peak_demand,abs(value))
                        sequence+=1;actions+=1
                    recorder.emit('action_request',sequence=sequence,observation_sequence=current.sequence,
                                  acceleration_m_s2=value,inference_s=latencies[-1])
                    current=bridge.advance(value,sequence)
                    recorder.observation(current)
                    observations+=1
                else:status='succeeded'
                diagnostics=bridge.diagnostics()
    except KeyboardInterrupt:
        interrupted=True;status='cancelled';error='worker_interrupted'
    except SandboxError:error='isolated_policy_failure'
    except QueueError:error='queue_lease_failure'
    except WorkerError:error='worker_guard_failure'
    except Exception:error='backend_failure'
    finally:
        if bridge is not None:
            try:diagnostics=bridge.diagnostics()
            except Exception:pass
            try:stopped=bridge.stop() is True
            except Exception:stopped=False;error=error or 'stop_unconfirmed';status='failed'
            finally:
                try:bridge.close()
                except Exception:stopped=False;error=error or 'close_failure';status='failed'
    if error is not None and status!='cancelled':status='failed'
    result={'backend':sensor_source,'execution_wall_budget_s':wall_budget,'max_acceleration_m_s2':approved_ceiling,'max_abs_requested_acceleration_m_s2':peak_demand,'stopped':stopped,'error':error,'actions':actions,'observations':observations,
            'elapsed_wall_s':time.monotonic()-began,'max_inference_s':max(latencies,default=0),**diagnostics}
    # An expired/uncertain lease is not retried or cleared. Queue recovery blocks
    # an active rig; only an authenticated operator can confirm physical recovery.
    result['recording']={'status':'local_pending_upload' if recorder is not None else 'unavailable'}
    finish_error=None
    try:finished=queue.finish(identifier,worker,lease,status,result)
    except Exception as exc:finish_error=exc;finished=None
    # Hardware is stopped before any ZIP creation or network upload. The durable
    # local spool survives a portal outage or expired lease; upload is artifact-only.
    if recorder is not None:
        try:
            recorder.emit('outcome',status=status,result=result)
            bundle=recorder.finalize(status,result)
            uploaded=queue.put_recording(identifier,worker,lease,bundle.read_bytes())
            if finished is not None:finished=uploaded
        except Exception:
            # The durable queue and response retain local_pending_upload. This
            # describes preserved local data awaiting manual retry, not success.
            pass
    if finish_error is not None:raise finish_error
    if interrupted:raise KeyboardInterrupt()
    return finished

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--local-root');source.add_argument('--portal')
    parser.add_argument('--token-file');parser.add_argument('--worker',default='worker')
    parser.add_argument('--rig-id',required=True);parser.add_argument('--backend',choices=('simulation','hardware'),default='simulation')
    parser.add_argument('--port');parser.add_argument('--rate',type=int,default=100,choices=(100,250,500,1000))
    parser.add_argument('--log-dir',default='runs/portal-hardware');parser.add_argument('--once',action='store_true')
    parser.add_argument('--spool-root')
    parser.add_argument('--enable-reservations',action='store_true',help='enable reservation gating for a local queue')
    parser.add_argument('--sensing-url',help='optional trusted developer-stream service origin to record independently')
    parser.add_argument('--recording-root',help='persistent run spool; defaults local queue recording-spool or runs/portal-recordings')
    parser.add_argument('--max-acceleration',type=float,help='trusted ceiling (0,25] m/s²; defaults simulation25, hardware0.25')
    args=parser.parse_args(argv)
    if args.max_acceleration is not None:
        try:validate_acceleration_ceiling(args.max_acceleration)
        except SandboxError as exc:parser.error(str(exc))
    if args.portal and not args.token_file:parser.error('--portal requires --token-file')
    if args.backend=='hardware' and not args.port:parser.error('--backend hardware requires --port')
    queue=Store(args.local_root,reservations_enabled=args.enable_reservations) if args.local_root else RemoteQueue(args.portal,Path(args.token_file).read_text().strip())
    bridge=SimulationBridge if args.backend=='simulation' else lambda:HardwareBridge(args.port,rate_hz=args.rate,log_dir=args.log_dir)
    sensor_source='simulation' if args.backend=='simulation' else 'magnetic-step'
    try:
        while True:
            result=run_once(queue,args.worker,args.rig_id,bridge_factory=bridge,sensor_source=sensor_source,spool_root=args.spool_root,max_acceleration=args.max_acceleration,recording_root=args.recording_root,sensing_url=args.sensing_url)
            if result is not None:print(canonical_json(result),flush=True)
            if args.once:return 0 if result is None or result['status']=='succeeded' else 1
            if result is None:time.sleep(.5)
    except KeyboardInterrupt:return 130
    except (QueueError,WorkerError):
        print('worker stopped: queue lease or recovery requires operator attention',file=__import__('sys').stderr)
        return 1
