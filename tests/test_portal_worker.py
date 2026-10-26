"""Trusted worker queue/broker integration with real pipe IPC and simulation/PTYS."""
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from cartpole_sdk.portal.queue import Store, QueueError
from cartpole_sdk.portal.sandbox import PolicyChannel, SandboxError
from cartpole_sdk.portal.worker import run_once, SimulationBridge, HardwareBridge, RemoteQueue
from cartpole_sdk.rig import Rig
from test_rig import Firmware, FDTransport

class TrustedPipeFixture:
    """A test-only trusted child; production always uses the bwrap launcher."""
    value=.1
    def __init__(self,source,**kwargs):
        self.source=source
        self.max_acceleration=kwargs.get('max_acceleration',.25)
    def launch(self):
        code='import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if r["type"]=="reset":print(json.dumps({"type":"reset_ack","nonce":r["nonce"]}),flush=True)\n else:print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":'+str(self.value)+'}),flush=True)\n'
        process=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        return PolicyChannel(process,action_timeout=.05,max_acceleration=self.max_acceleration)

class WorkerTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def submit(self,source='simulation'):
        job=self.store.submit('alice','one',b'never imported in broker','policy.py',source,.1)
        if source=='magnetic-step':self.store.approve(job['id'],'operator',artifact=job['artifact'],sensor_source=source,duration=job['duration'])
        return job
    def test_simulation_job_uses_selected_samples_and_records_bounded_result(self):
        job=self.submit()
        result=run_once(self.store,'w','sim',bridge_factory=SimulationBridge,sandbox_factory=TrustedPipeFixture,sensor_source='simulation')
        self.assertEqual(result['status'],'succeeded')
        self.assertTrue(result['result']['stopped'])
        self.assertEqual(result['result']['backend'],'simulation')
        self.assertGreater(result['result']['actions'],0)
        self.assertEqual(self.store.get(job['id'],'alice')['status'],'succeeded')
    def test_outbound_http_worker_claim_fetch_and_finish_end_to_end(self):
        from cartpole_sdk.portal.server import make_server
        server=make_server(self.store,{'test-worker-token-secret':('w','worker')},port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.submit()
            remote=RemoteQueue(f'http://127.0.0.1:{server.server_port}','test-worker-token-secret')
            result=run_once(remote,'w','simulation',bridge_factory=SimulationBridge,sandbox_factory=TrustedPipeFixture,sensor_source='simulation',recording_root=Path(self.tmp.name)/'spool')
            self.assertEqual(result['status'],'succeeded')
            self.assertTrue(result['result']['stopped'])
        finally:server.shutdown();server.server_close();thread.join()

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('bwrap'),'actual Linux isolation required')
    def test_real_isolated_simulation_queue_worker(self):
        source=b'from cartpole_sdk.contracts import Acceleration\nclass Policy:\n def reset(self,session): pass\n def act(self,observation): return Acceleration(0)\ndef create_policy(): return Policy()\n'
        job=self.store.submit('alice','real-isolated',source,'zero.py','simulation',.1)
        result=run_once(self.store,'w','isolated-simulation',sensor_source='simulation')
        self.assertEqual(result['status'],'succeeded')
        self.assertTrue(result['result']['stopped'])
        self.assertGreater(result['result']['actions'],0)
        self.assertEqual(self.store.get(job['id'],'alice')['status'],'succeeded')

    def test_simulation_raw_executor_initial_none_fails_closed(self):
        class NoneFixture(TrustedPipeFixture):
            def launch(self):
                channel=super().launch()
                original=channel.act
                def act(observation):original(observation);return None
                channel.act=act
                return channel
        self.submit()
        result=run_once(self.store,'w','sim',sandbox_factory=NoneFixture,sensor_source='simulation')
        self.assertEqual(result['status'],'failed')
        # The shared rig profile begins with the same short ARM lease as the rig.
        self.assertEqual(result['result']['simulation_fault'],'action lease expired')
        self.assertTrue(result['result']['stopped'])

    def test_stale_start_response_cannot_arm_after_lease_reassigned(self):
        class ReassignedStore(Store):
            def start(self,identifier,worker,lease,**kwargs):
                stale=super().start(identifier,worker,lease,**kwargs)
                self.recover(now=time.time()+100)
                self.release_block('sim',stopped_confirmed=True)
                self.claim('new-worker','sim')
                return stale
        queue=ReassignedStore(self.tmp.name)
        queue.submit('alice','old',b'x','old.py','simulation',.1)
        queue.submit('alice','next',b'y','next.py','simulation',.1)
        armed=[]
        class TrackingBridge(SimulationBridge):
            def arm(self,duration):armed.append(duration)
        with self.assertRaises(QueueError):run_once(queue,'w','sim',bridge_factory=TrackingBridge,sandbox_factory=TrustedPipeFixture)
        self.assertEqual(armed,[])

    def test_delayed_final_heartbeat_cannot_arm_after_reassignment(self):
        class ReassignedHeartbeat(Store):
            def heartbeat(self,identifier,worker,lease,**kwargs):
                stale=super().heartbeat(identifier,worker,lease,**kwargs)
                time.sleep(.3)
                self.recover(now=time.time()+100)
                self.release_block('sim',stopped_confirmed=True)
                self.claim('new-worker','sim')
                return stale
        queue=ReassignedHeartbeat(self.tmp.name)
        queue.submit('alice','old',b'x','old.py','simulation',5)
        queue.submit('alice','next',b'y','next.py','simulation',5)
        armed=[]
        class TrackingBridge(SimulationBridge):
            def arm(self,duration):armed.append(duration)
        with self.assertRaises(QueueError):run_once(queue,'w','sim',bridge_factory=TrackingBridge,sandbox_factory=TrustedPipeFixture)
        self.assertEqual(armed,[])

    def test_remote_redirect_cannot_forward_bearer_to_another_origin(self):
        received=[]
        class Sink(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200);self.end_headers();self.wfile.write(b'{}')
        sink=ThreadingHTTPServer(('127.0.0.1',0),Sink)
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(302);self.send_header('Location',f'http://127.0.0.1:{sink.server_port}/sink');self.end_headers()
        origin=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (origin,sink)]
        for thread in threads:thread.start()
        try:
            remote=RemoteQueue(f'http://127.0.0.1:{origin.server_port}','synthetic-review-token')
            with self.assertRaises(ValueError):remote._request('/api/redirect')
            self.assertEqual(received,[])
        finally:
            for server in (origin,sink):server.shutdown();server.server_close()
            for thread in threads:thread.join()

    def test_remote_slow_response_cannot_extend_absolute_call_timeout(self):
        class Slow(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
                try:
                    for _ in range(100):self.wfile.write(b' ');self.wfile.flush();time.sleep(.02)
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Slow);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            remote=RemoteQueue(f'http://127.0.0.1:{server.server_port}','test-token',timeout=.1)
            began=time.monotonic()
            with self.assertRaises(ValueError):remote._request('/api/slow')
            self.assertLess(time.monotonic()-began,.3)
        finally:server.shutdown();server.server_close();thread.join()

    def test_simulation_default_accepts_controller_startup_demand(self):
        class KickFixture(TrustedPipeFixture):value=1.
        self.submit()
        result=run_once(self.store,'w','sim',sandbox_factory=KickFixture)
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(result['result']['max_acceleration_m_s2'],25.)
        self.assertEqual(result['result']['executor']['raw_acceleration_m_s2'],1.)
        self.assertEqual(result['result']['max_abs_requested_acceleration_m_s2'],1.)

    def test_tampered_output_above_operator_ceiling_fails_before_action(self):
        class TamperedFixture(TrustedPipeFixture):
            def launch(self):
                channel=super().launch()
                original=channel.act
                def act(observation):original(observation);return 2.
                channel.act=act;return channel
        self.submit()
        result=run_once(self.store,'w','sim',sandbox_factory=TamperedFixture,max_acceleration=1.)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['result']['actions'],0)
        self.assertTrue(result['result']['stopped'])

    def test_invalid_trusted_ceiling_does_not_claim_job(self):
        job=self.submit()
        for value in (True,0,-1,25.1,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):run_once(self.store,'w','sim',max_acceleration=value)
        self.assertEqual(self.store.get(job['id'],'alice')['status'],'pending')

    def test_hardware_default_rejects_controller_demand_before_wire_action(self):
        class KickFixture(TrustedPipeFixture):value=1.
        fw=Firmware();fw.flags |=8
        try:
            with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
                self.submit('magnetic-step')
                result=run_once(self.store,'w','rig',bridge_factory=lambda:HardwareBridge(rig=rig),sandbox_factory=KickFixture,sensor_source='magnetic-step')
                self.assertEqual(result['status'],'failed')
                self.assertEqual(result['result']['max_acceleration_m_s2'],.25)
                self.assertFalse(any(c[1]=='A' for c in fw.commands))
                self.assertFalse(fw.flags&2)
        finally:fw.close()

    @unittest.skipUnless(sys.platform=='linux' and shutil.which('bwrap'),'actual Linux isolation required')
    def test_real_isolated_learned_simulation_queue_worker(self):
        source_path=Path(__file__).resolve().parents[1]/'evidence'/'phase5'/'learned-policy-simulation.py'
        self.assertTrue(source_path.is_file(),'copy the exported learned policy artifact for target acceptance')
        source=source_path.read_bytes()
        job=self.store.submit('alice','real-learned',source,'learned-policy.py','simulation',10.)
        result=run_once(self.store,'w','isolated-learned-simulation')
        self.assertEqual(result['status'],'succeeded',result['result'])
        self.assertTrue(result['result']['stopped'])
        self.assertEqual(result['result']['max_acceleration_m_s2'],25.)
        self.assertGreater(result['result']['max_abs_requested_acceleration_m_s2'],.25)
        self.assertGreaterEqual(result['result']['actions'],900)
        self.assertEqual(result['result']['simulation_time_ns'],10_000_000_000)
        self.assertIn('theta',result['result']['ground_truth'])
        self.assertEqual(self.store.get(job['id'],'alice')['status'],'succeeded')

    def test_slow_simulation_uses_shared_finite_wall_budget(self):
        configured=[]
        class CapturingFixture(TrustedPipeFixture):
            def __init__(self,source,**kwargs):
                configured.append(kwargs['wall_seconds']);super().__init__(source,**kwargs)
        class SlowSimulation(SimulationBridge):
            def advance(self,value,sequence):
                began=time.monotonic()
                following=super().advance(value,sequence)
                # Pace the whole physics advance, rather than adding a delay to
                # target-dependent physics cost: 20 * 22ms = 440ms minimum.
                time.sleep(max(0,.022-(time.monotonic()-began)))
                return following
        self.store.submit('alice','slow',b'test-only pipe fixture','slow.py','simulation',.2)
        result=run_once(self.store,'w','sim',bridge_factory=SlowSimulation,sandbox_factory=CapturingFixture)
        self.assertEqual(result['status'],'succeeded',result['result'])
        self.assertEqual(configured,[.4])
        self.assertEqual(result['result']['execution_wall_budget_s'],.4)
        self.assertEqual(result['result']['simulation_time_ns'],200_000_000)

    def test_failed_reset_never_arms_and_releases_stopped_job(self):
        class ResetFailure(TrustedPipeFixture):
            def launch(self):raise SandboxError('reset failed')
        self.submit();result=run_once(self.store,'w','sim',bridge_factory=SimulationBridge,sandbox_factory=ResetFailure,sensor_source='simulation')
        self.assertEqual(result['status'],'failed');self.assertTrue(result['result']['stopped'])
    def test_worker_interrupt_records_cancelled_and_stopped_job(self):
        class Interrupt(TrustedPipeFixture):
            def launch(self):raise KeyboardInterrupt()
        job=self.submit()
        with self.assertRaises(KeyboardInterrupt):run_once(self.store,'w','sim',bridge_factory=SimulationBridge,sandbox_factory=Interrupt,sensor_source='simulation')
        finished=self.store.get(job['id'],'alice')
        self.assertEqual(finished['status'],'cancelled');self.assertTrue(finished['result']['stopped'])

    def test_default_sandbox_on_mac_fails_job_without_importing_artifact(self):
        if sys.platform=='linux':self.skipTest('non-Linux fail-closed case')
        self.submit();result=run_once(self.store,'w','sim',bridge_factory=SimulationBridge,sensor_source='simulation')
        self.assertEqual(result['status'],'failed');self.assertEqual(result['result']['error'],'isolated_policy_failure')
    def test_hardware_bridge_refuses_no_switch_profile_and_never_auto_centers(self):
        fw=Firmware()
        try:
            with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
                bridge=HardwareBridge(rig=rig)
                with self.assertRaises(ValueError):bridge.prepare(.1,'x')
                self.assertFalse(any(c[1] in ('ARM','MODE','CENTER','SWITCHES','CLEAR','HOME') for c in fw.commands))
        finally:fw.close()
    def test_hardware_queue_reset_ack_precedes_explicit_arm_and_stop_finally(self):
        fw=Firmware();fw.flags |=8
        try:
            with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
                self.submit('magnetic-step')
                result=run_once(self.store,'w','rig',bridge_factory=lambda:HardwareBridge(rig=rig),sandbox_factory=TrustedPipeFixture,sensor_source='magnetic-step')
                self.assertEqual(result['status'],'succeeded')
                self.assertFalse(fw.flags&2)
                self.assertTrue(any(c[1]=='ARM' for c in fw.commands))
                self.assertFalse(any(c[1] in ('CENTER','SWITCHES','CLEAR','HOME','MODE') for c in fw.commands))
        finally:fw.close()
