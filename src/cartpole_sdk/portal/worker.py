"""Trusted outbound pull worker. Uploaded modules are never imported here."""
import argparse
import base64
from dataclasses import asdict, replace
import hashlib
from functools import partial
import math
import os
import re
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
from .artifacts import MAX_UPLOAD_BYTES, MAX_ENVELOPE_BYTES, prepare_artifact
from .sandbox import Sandbox, SandboxError, validate_acceleration_ceiling

class WorkerError(ValueError):pass
class ClaimUnavailable(WorkerError):pass

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
    def _request(self,path,body=None,*,binary=None,lease=None,response_limit=None,raw_response=False,deadline_timeout=None):
        if not path.startswith('/api/') or '?' in path or '#' in path:
            raise WorkerError('invalid portal API path')
        data=binary if binary is not None else (None if body is None else canonical_json(body).encode())
        artifact_response=re.fullmatch(r'/api/jobs/[a-f0-9]{32}/artifact',path) is not None and data is None
        response_limit=response_limit if response_limit is not None else (MAX_ENVELOPE_BYTES if artifact_response else 100000)
        request_timeout=30 if binary is not None or artifact_response or path.endswith('/start') else self.timeout
        if deadline_timeout is not None:request_timeout=min(request_timeout,deadline_timeout)
        if not self._slots.acquire(blocking=False):raise WorkerError('portal request already pending')
        deadline=time.monotonic()+request_timeout
        replies=thread_queue.Queue(maxsize=1);cancel=threading.Event();state={}
        def request():
            connection=None;phase='connect'
            try:
                kind=http.client.HTTPSConnection if self.parts.scheme=='https' else http.client.HTTPConnection
                connection=kind(self.parts.hostname,self.parts.port,timeout=request_timeout)
                state['connection']=connection
                connection.connect()
                state['socket']=connection.sock
                if cancel.is_set():raise WorkerError('portal deadline exceeded')
                phase='request'
                connection.request('GET' if data is None else 'POST',path,body=data,
                    headers={'Authorization':'Bearer '+self.token,**({'Content-Type':'application/zip','X-Worker-Lease':lease} if binary is not None else ({'Content-Type':'application/json'} if data is not None else {}))})
                phase='response_headers'
                response=connection.getresponse()
                if not 200<=response.status<300:raise WorkerError('portal status rejected')
                # Fixed API endpoints never need redirects. HTTPConnection does not
                # follow them or forward a bearer token to another origin.
                length=response.getheader('Content-Length')
                if response.getheader('Transfer-Encoding') is not None or length is None or not length.isdecimal() or not 0<=int(length)<=response_limit:
                    raise WorkerError('invalid portal response framing')
                phase='response_body'
                raw=bytearray()
                while len(raw)<int(length):
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or cancel.is_set():raise WorkerError('portal deadline exceeded')
                    state['socket'].settimeout(remaining)
                    chunk=response.read1(min(4096,int(length)-len(raw)))
                    if not chunk:raise WorkerError('incomplete portal response')
                    raw.extend(chunk)
                value=bytes(raw) if raw_response else strict_json_loads(raw.decode())
                if not cancel.is_set():replies.put_nowait((value,None))
            except Exception as exc:
                failure=WorkerError('portal request failed')
                failure.diagnostic={'phase':phase,'exception_type':type(exc).__name__}
                if not cancel.is_set():replies.put_nowait((None,failure))
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
    def claim(self,worker,rig,*,sensor_source=None):
        try:return self._request('/api/claim',{'rig':rig,'sensor_source':sensor_source})['job']
        except WorkerError as exc:
            # A lost response may have claimed an unarmed job. Only the queue's
            # ordinary expiry can release it; expired running leases stay blocked.
            raise ClaimUnavailable('claim unavailable; connectivity or operator recovery required') from exc
    def fetch(self,job,worker):
        value=self._request('/api/jobs/'+job['id']+'/artifact')
        try:source=base64.b64decode(value['source_base64'],validate=True)
        except (KeyError,ValueError) as exc:raise WorkerError('invalid artifact response') from exc
        if len(source)>MAX_UPLOAD_BYTES or value['sha256']!=job['artifact'] or hashlib.sha256(source).hexdigest()!=job['artifact']:raise WorkerError('artifact digest mismatch')
        return source
    def start(self,identifier,worker,token):return self._request('/api/jobs/'+identifier+'/start',{'lease':token})
    def heartbeat(self,identifier,worker,token):return self._request('/api/jobs/'+identifier+'/heartbeat',{'lease':token})
    def finish(self,identifier,worker,token,status,result):return self._request('/api/jobs/'+identifier+'/finish',{'lease':token,'status':status,'result':result})

from cartpole_sdk.sim.portal_bridge import ProfileSimulationBridge as SimulationBridge

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

class _SetupLease:
    """Renew only the short claimed lease while bounded unarmed setup runs."""
    def __init__(self,queue,identifier,worker,lease,*,renew_required=True):
        self.thread=None
        self.stop_event=threading.Event();self.error=None
        if not renew_required:return
        def renew():
            while not self.stop_event.wait(.4):
                try:
                    job=queue.heartbeat(identifier,worker,lease)
                    if job['status']!='claimed' or job['cancel_requested']:raise WorkerError('setup authority revoked')
                except Exception as exc:
                    self.error=exc;return
        self.thread=threading.Thread(target=renew,daemon=True)
        self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread is None:return
        self.thread.join(1.5)
        if self.thread.is_alive():raise WorkerError('setup heartbeat did not finish')
        if self.error is not None:raise WorkerError('setup authority revoked') from self.error

class RunAuthorityError(WorkerError):pass

class _RunLease:
    """Network renewal stays off the action loop; every action checks freshness."""
    def __init__(self,queue,identifier,worker,lease,rig,*,confirmed_at,interval=.25,max_age=1.):
        self.stop_event=threading.Event();self.error=None;self.cancelled=False
        self.confirmed_at=confirmed_at;self.max_age=max_age
        self.renew_started_at=None;self.renew_finished_at=None;self.renew_count=0
        def renew():
            while not self.stop_event.wait(interval):
                began=time.monotonic();self.renew_started_at=began
                try:
                    job=queue.heartbeat(identifier,worker,lease)
                    if (job['id']!=identifier or job['worker']!=worker or job['lease']!=lease or
                            job['rig']!=rig or job['status']!='running'):
                        raise RunAuthorityError('runtime lease identity mismatch')
                    self.cancelled=bool(job['cancel_requested'])
                    # Age from request start, so delayed replies cannot refresh
                    # authority using their later arrival time.
                    self.confirmed_at=began
                    self.renew_finished_at=time.monotonic();self.renew_count+=1
                    if self.cancelled:return
                except Exception as exc:
                    self.error=exc;return
        self.thread=threading.Thread(target=renew,daemon=True,name='portal-run-lease')
        self.thread.start()
    def check(self):
        if self.error is not None:raise RunAuthorityError('runtime heartbeat failed') from self.error
        if time.monotonic()-self.confirmed_at>self.max_age:
            # In-memory code locations only: no locals, source reads, or I/O on
            # the stop path. This distinguishes a blocked socket from scheduling.
            import sys
            failure=RunAuthorityError('runtime authority stale')
            failure.thread_locations=[]
            for thread,frame in list(sys._current_frames().items())[:16]:
                functions=[];locations=[]
                for _ in range(10):
                    if frame is None:break
                    functions.append(frame.f_code.co_name)
                    locations.append([frame.f_code.co_filename.rsplit('/',1)[-1],frame.f_lineno])
                    frame=frame.f_back
                failure.thread_locations.append({'thread':thread,'functions':functions,'locations':locations})
            raise failure
        return not self.cancelled
    def close(self):
        self.stop_event.set();self.thread.join(1.5)
        if self.thread.is_alive():raise RunAuthorityError('runtime heartbeat did not finish')

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
    status='failed';error=None;authority_failure=None;stopped=True;latencies=[];actions=0;observations=0;diagnostics={};peak_demand=0.;wall_budget=None
    began=time.monotonic();interrupted=False;recorder=None;run_lease=None;numeric_backend=None;scheduling=None;setup_lease=_SetupLease(queue,identifier,worker,lease,renew_required=job.get('setup_heartbeat_required',True))
    recording_root=recording_root or (queue.root/'recording-spool' if isinstance(queue,Store) else 'runs/portal-recordings')
    try:
        recorder=RunRecorder(recording_root,job)
        recorder.emit('attempt',backend=sensor_source,max_acceleration_m_s2=approved_ceiling)
        if sensing_url is not None:
            recorder.start_sensing(sensing_url,job['duration']+35,detailed=job.get('recording','standard')=='detailed')
        source=queue.artifact(job['artifact']) if isinstance(queue,Store) else queue.fetch(job,worker)
        if len(source)>MAX_UPLOAD_BYTES or hashlib.sha256(source).hexdigest()!=job['artifact']:raise WorkerError('artifact digest mismatch')
        stopped=False  # backend factory may acquire hardware even if it raises
        bridge=bridge_factory()
        if bridge.kind!=job['source'] or bridge.kind!=sensor_source:
            raise WorkerError('worker source selection mismatch')
        wall_budget=execution_wall_seconds(bridge.kind,job['duration'])
        current=bridge.prepare(job['duration'],identifier)
        recorder.emit('session',session=asdict(bridge.session))
        recorder.observation(current)
        recorded_observation=current
        recorder.emit('backend_start',diagnostics=bridge.diagnostics())
        with tempfile.TemporaryDirectory(prefix='cartpole-policy-',dir=spool_root) as spool:
            inspection=prepare_artifact(source,job['filename'],spool)
            recorder.emit('artifact',sha256=job['artifact'],inspection=inspection)
            if (inspection['kind']=='actor-json' and isinstance(bridge,SimulationBridge)
                    and inspection['angle_source']!=bridge.env.observation_config.angle_source):
                error='simulation_profile_mismatch'
                raise WorkerError('actor angle source differs from simulation profile')
            if inspection['kind']=='actor-json' and isinstance(bridge,HardwareBridge):
                # Data-only admission; no uploaded code or neural loader executes here.
                from types import SimpleNamespace
                from cartpole_sdk.rig.neural_runner import validate_live_executor
                from cartpole_sdk.policies.rig_observation import observation_contract
                actor=strict_json_loads(source.decode())
                validate_live_executor(bridge.rig,SimpleNamespace(actor=actor,
                    executor_parameters=actor.get('executor_parameters'),
                    observation_contract=actor.get('observation_contract') or observation_contract(angle_source=actor['angle_source'])))
            isolator=sandbox_factory(Path(spool),artifact_kind=inspection['kind'],sensor_source=sensor_source,
                    wall_seconds=wall_budget,max_acceleration=approved_ceiling)
            realtime=getattr(isolator,'realtime',False)
            scheduling={'policy':'RR' if realtime else 'OTHER','priority':1 if realtime else 0,
                        'cpu':getattr(isolator,'cpu_affinity',None),'hard_rttime_us':500000 if realtime else None,
                        'startup_hard_rttime_us':(1250000 if inspection['kind']=='actor-json' else 500000) if realtime else None,
                        'hard_rtprio':1 if realtime else None,'action_wall_timeout_s':getattr(isolator,'action_timeout',None)}
            recorder.emit('sandbox_runtime',scheduling=scheduling)
            if inspection['kind']=='actor-json':
                numeric_backend='numpy-einsum' if getattr(isolator,'numpy_root',None) is not None else 'python'
                recorder.emit('numeric_runtime',configured_backend=numeric_backend)
            with isolator.launch() as child:
                child.reset(bridge.session)  # no physical arm before strict reset ACK
                setup_lease.stop()
                recorder.emit('execution_ready',preparation_wall_s=time.monotonic()-began,requested_duration_s=job['duration'])
                original_duration=job['duration']
                job=queue.start(identifier,worker,lease)
                # A successful but delayed start response is not current authority.
                # Revalidate the actual lease after setup, immediately before ARM.
                authority_began=time.monotonic()
                job=queue.heartbeat(identifier,worker,lease)
                if time.monotonic()-authority_began>.25:
                    raise WorkerError('final lease authority response too old')
                if job['id']!=identifier or job['worker']!=worker or job['rig']!=rig_id or job['lease']!=lease or job['status']!='running':
                    raise WorkerError('worker lease identity mismatch')
                if job['cancel_requested']:raise WorkerError('job cancelled')
                if 'runtime_remaining_s' in job and job['runtime_remaining_s']-(time.monotonic()-authority_began)<wall_budget+.1:
                    raise WorkerError('insufficient authority for full requested run')
                remaining_duration=original_duration
                run_lease=_RunLease(queue,identifier,worker,lease,rig_id,confirmed_at=authority_began)
                try:
                    child.begin_run()
                    motion_began=time.monotonic()
                    bridge.arm(remaining_duration)
                    if isinstance(bridge,HardwareBridge):current=bridge.selected()
                    wall_end=motion_began+wall_budget+min(.5,job['duration'])
                    sequence=0
                    while not bridge.complete():
                        if time.monotonic()>=wall_end:raise WorkerError('run wall deadline exceeded')
                        if not run_lease.check():status='cancelled';break
                        if current!=recorded_observation:
                            recorder.observation(current)
                            recorded_observation=current
                        action_began=time.monotonic()
                        recorder.emit('policy_call',observation_sequence=current.sequence)
                        try:
                            value=child.act(current)
                        except BaseException:
                            elapsed=time.monotonic()-action_began
                            latencies.append(elapsed)
                            recorder.emit('policy_failure',observation_sequence=current.sequence,
                                          inference_s=elapsed)
                            raise
                        else:
                            latencies.append(time.monotonic()-action_began)
                        if value is not None:
                            if type(value) not in (int,float) or abs(value)>approved_ceiling or not math.isfinite(value):raise SandboxError('policy acceleration exceeds trusted worker ceiling')
                            peak_demand=max(peak_demand,abs(value))
                            sequence+=1;actions+=1
                        recorder.emit('action_request',sequence=sequence,observation_sequence=current.sequence,
                                      acceleration_m_s2=value,inference_s=latencies[-1])
                        if not run_lease.check():status='cancelled';break
                        current=bridge.advance(value,sequence)
                        recorder.observation(current)
                        recorded_observation=current
                        if job.get('recording','standard')=='detailed' and isinstance(bridge,HardwareBridge):
                            # The reader can advance between SDK selection and this
                            # cached snapshot. Read once and preserve its own tick.
                            state=bridge.rig.state
                            recorder.emit('board_state',nearest_observation_sequence=current.sequence,
                                snapshot_matches_observation=state.unwrapped_tick==current.sequence,
                                sampling='independent latest board snapshot; join by state.unwrapped_tick and original timestamps',
                                state=asdict(state))
                        observations+=1
                    else:status='succeeded'
                finally:
                    # STOP while still inside the policy context: terminating its
                    # process and deleting its project can take longer than the
                    # firmware action/duration margin.
                    try:stopped=bridge.stop() is True
                    except Exception:stopped=False
                    if not stopped:error=error or 'stop_unconfirmed';status='failed'
                    try:diagnostics=bridge.diagnostics()
                    except Exception:pass
                    if diagnostics.get('board_state',{}).get('fault',0):
                        error='hardware_executor_fault';status='failed'
    except KeyboardInterrupt:
        interrupted=True;status='cancelled';error='worker_interrupted'
    except SandboxError:error='isolated_policy_failure'
    except QueueError:error='queue_lease_failure'
    except RunAuthorityError as exc:
        error='runtime_authority_failure'
        cause=exc.__cause__
        authority_failure={'thread_locations':getattr(exc,'thread_locations',None),'reason':str(exc),'cause_type':type(cause).__name__ if cause else None,
            'heartbeat_age_s':None if run_lease is None else time.monotonic()-run_lease.confirmed_at,
            'transport':getattr(cause,'diagnostic',None),
            'renew_started_at':run_lease.renew_started_at if run_lease else None,
            'renew_finished_at':run_lease.renew_finished_at if run_lease else None,
            'renew_count':run_lease.renew_count if run_lease else None}
    except WorkerError:error=error or 'worker_guard_failure'
    except Exception:error='backend_failure'
    finally:
        if run_lease is not None:run_lease.stop_event.set()
        if bridge is not None:
            # Also covers setup failures before entering the armed block.
            try:stopped=bridge.stop() is True
            except Exception:stopped=False
            if not stopped:error=error or 'stop_unconfirmed';status='failed'
            try:diagnostics=bridge.diagnostics()
            except Exception:pass
            if diagnostics.get('board_state',{}).get('fault',0):
                error='hardware_executor_fault';status='failed'
            try:bridge.close()
            except Exception:stopped=False;error=error or 'close_failure';status='failed'
        try:setup_lease.stop()
        except WorkerError:
            if error is None:error='setup_authority_failure';status='failed'
    if run_lease is not None:
        try:run_lease.close()  # physical STOP precedes any network-thread join
        except RunAuthorityError:error=error or 'runtime_authority_failure';status='failed'
    if error is not None and status!='cancelled':status='failed'
    result={'backend':sensor_source,'sandbox_scheduling':scheduling,'numeric_inference_backend':numeric_backend,'execution_wall_budget_s':wall_budget,'max_acceleration_m_s2':approved_ceiling,'max_abs_requested_acceleration_m_s2':peak_demand,'stopped':stopped,'error':error,'actions':actions,'observations':observations,
            'elapsed_wall_s':time.monotonic()-began,'max_inference_s':max(latencies,default=0),**diagnostics}
    # An expired/uncertain lease is not retried or cleared. Queue recovery blocks
    # an active rig; only an authenticated operator can confirm physical recovery.
    result['recording']={'status':'local_pending_upload' if recorder is not None else 'unavailable'}
    if authority_failure is not None:result['authority_failure']=authority_failure
    finish_error=None
    try:
        if run_lease is not None and run_lease.thread.is_alive():raise RunAuthorityError('cannot finish while renewal is pending')
        finished=queue.finish(identifier,worker,lease,status,result)
        # Cancellation can arrive after the last action/STOP. Persist the queue's
        # committed outcome in the bundle, including its terminal status override.
        status=finished['status']
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
    # Match the operator console: keep the serial I/O and heartbeat threads from
    # waiting a default 5ms GIL timeslice inside the 20ms action lifetime.
    import sys
    previous=sys.getswitchinterval()
    try:
        sys.setswitchinterval(.001)
        return _main(argv)
    finally:sys.setswitchinterval(previous)


def _main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--local-root');source.add_argument('--portal')
    parser.add_argument('--token-file');parser.add_argument('--worker',default='worker')
    parser.add_argument('--rig-id',required=True);parser.add_argument('--backend',choices=('simulation','hardware'),default='simulation')
    parser.add_argument('--port');parser.add_argument('--rate',type=int,default=100,choices=(100,250,500,1000))
    parser.add_argument('--log-dir',default='runs/portal-hardware');parser.add_argument('--once',action='store_true')
    parser.add_argument('--spool-root')
    parser.add_argument('--sandbox-realtime',action='store_true',help='trusted RR1 child, requires RR10 broker on separate single CPU; hard uninterrupted realtime CPU limit 500ms; independent 10ms action wall deadline')
    parser.add_argument('--sandbox-cpu',type=int,help='trusted dedicated CPU index for the isolated policy child')
    parser.add_argument('--numpy-root',help='trusted readonly NumPy package root compatible with sandbox Python; enables prewarmed numeric inference')
    parser.add_argument('--enable-reservations',action='store_true',help='enable reservation gating for a local queue')
    parser.add_argument('--sensing-url',help='optional trusted developer-stream service origin to record independently')
    parser.add_argument('--recording-root',help='persistent run spool; defaults local queue recording-spool or runs/portal-recordings')
    parser.add_argument('--max-acceleration',type=float,help='trusted ceiling (0,25] m/s²; defaults simulation25, hardware0.25')
    args=parser.parse_args(argv)
    if args.max_acceleration is not None:
        try:validate_acceleration_ceiling(args.max_acceleration)
        except SandboxError as exc:parser.error(str(exc))
    if args.sandbox_cpu is not None and not 0<=args.sandbox_cpu<(os.cpu_count() or 1):parser.error('--sandbox-cpu must name an available processor')
    if args.sandbox_realtime and args.sandbox_cpu is None:parser.error('--sandbox-realtime requires --sandbox-cpu')
    if args.numpy_root:
        args.numpy_root=str(Path(args.numpy_root).resolve())
        if not all((Path(args.numpy_root)/name).is_dir() for name in ('numpy','numpy.libs')):parser.error('--numpy-root requires numpy and numpy.libs directories')
    if args.portal and not args.token_file:parser.error('--portal requires --token-file')
    if args.backend=='hardware' and not args.port:parser.error('--backend hardware requires --port')
    queue=Store(args.local_root,reservations_enabled=args.enable_reservations) if args.local_root else RemoteQueue(args.portal,Path(args.token_file).read_text().strip())
    bridge=SimulationBridge if args.backend=='simulation' else lambda:HardwareBridge(args.port,rate_hz=args.rate,log_dir=args.log_dir)
    sensor_source='simulation' if args.backend=='simulation' else 'magnetic-step'
    if args.backend=='simulation':
        warm=SimulationBridge()
        try:warm.prepare(.05,'portal-prewarm')
        finally:warm.close()
    claim_backoff=1.
    try:
        while True:
            try:
                result=run_once(queue,args.worker,args.rig_id,sandbox_factory=partial(Sandbox,numpy_root=args.numpy_root,cpu_affinity=args.sandbox_cpu,realtime=args.sandbox_realtime),bridge_factory=bridge,sensor_source=sensor_source,spool_root=args.spool_root,max_acceleration=args.max_acceleration,recording_root=args.recording_root,sensing_url=args.sensing_url)
            except ClaimUnavailable:
                print('portal claim unavailable; retrying without clearing leases; check connectivity or operator recovery',file=__import__('sys').stderr,flush=True)
                if args.once:return 1
                time.sleep(claim_backoff);claim_backoff=min(5.,claim_backoff*2)
                continue
            claim_backoff=1.
            if result is not None:
                print(canonical_json(result),flush=True)
                outcome=result.get('result') or {}
                if args.backend=='hardware' and (outcome.get('stopped') is not True or
                        outcome.get('error') in ('hardware_executor_fault','stop_unconfirmed') or
                        (outcome.get('board_state') or {}).get('fault',0)):
                    print('hardware worker stopped: rig fault or STOP not confirmed; operator recovery required',file=__import__('sys').stderr,flush=True)
                    return 1
            if args.once:return 0 if result is None or result['status']=='succeeded' else 1
            if result is None:time.sleep(.5)
    except KeyboardInterrupt:return 130
    except (QueueError,WorkerError):
        print('worker stopped: queue lease or recovery requires operator attention',file=__import__('sys').stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
