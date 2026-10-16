"""Transactional ownership, immutable uploads and crash-safe rig leases."""
import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from cartpole_sdk.portal.queue import Store, QueueError

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def submit(self, owner='alice', key='one', **kw):
        return self.store.submit(owner,key,b'def create_policy():\n    return None\n','policy.py','magnetic-step',.1,**kw)
    def test_idempotency_returns_same_job_and_binds_request(self):
        first=self.submit();self.assertEqual(self.submit()['id'],first['id'])
        with self.assertRaises(QueueError):self.store.submit('alice','one',b'changed','x.py','magnetic-step',.1)
        self.assertNotEqual(self.submit(owner='bob')['id'],first['id'])
    def test_artifact_content_addressed_immutable_and_bounded(self):
        job=self.submit();self.assertEqual(self.store.artifact(job['artifact']),b'def create_policy():\n    return None\n')
        with self.assertRaises(QueueError):self.store.submit('alice','big',b'x'*65537,'p.py','magnetic-step',.1)
        for filename in ('../p.py','x.zip','/tmp/x.py'):
            with self.assertRaises(QueueError):self.store.submit('alice',filename,b'x',filename,'magnetic-step',.1)
        with self.assertRaises(QueueError):self.store.artifact('../etc/passwd')
    def test_artifact_symlink_cannot_redirect_write(self):
        import hashlib
        source=b'x=1\n';sha=hashlib.sha256(source).hexdigest()
        outside=Path(self.tmp.name)/'sentinel';outside.write_bytes(b'keep')
        (Path(self.tmp.name)/'artifacts'/f'{sha}.py').symlink_to(outside)
        with self.assertRaises(QueueError):self.store.submit('alice','evil',source,'x.py','magnetic-step',.1)
        self.assertEqual(outside.read_bytes(),b'keep')
    def test_rejected_queue_limit_does_not_accumulate_orphan_uploads(self):
        for index in range(32):self.submit(key=f'job{index}')
        before=list((Path(self.tmp.name)/'artifacts').iterdir())
        with self.assertRaises(QueueError):self.store.submit('alice','overflow',b'unique rejected source','x.py','magnetic-step',.1)
        self.assertEqual(list((Path(self.tmp.name)/'artifacts').iterdir()),before)

    def test_source_filtered_worker_cannot_claim_other_backend_job(self):
        self.submit()
        self.assertIsNone(self.store.claim('w','sim-rig',sensor_source='simulation'))
        job=self.store.submit('alice','sim',b'x=1','x.py','simulation',.1)
        self.assertEqual(self.store.claim('w','sim-rig',sensor_source='simulation')['id'],job['id'])

    def test_owner_cannot_read_or_cancel_other_job(self):
        job=self.submit()
        with self.assertRaises(QueueError):self.store.get(job['id'],'bob')
        with self.assertRaises(QueueError):self.store.cancel(job['id'],'bob')
        self.assertEqual(self.store.cancel(job['id'],'alice')['status'],'cancelled')
    def test_atomic_claims_serialize_one_rig_across_threads(self):
        self.submit();self.submit(key='two')
        def claim(index):return Store(self.tmp.name).claim(f'worker{index}','rig1')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            claims=list(executor.map(claim,range(8)))
        self.assertEqual(sum(job is not None for job in claims),1)
    def test_lease_token_and_fixed_deadline_cannot_be_replaced(self):
        job=self.submit();claim=self.store.claim('w','r',now=100)
        with self.assertRaises(QueueError):self.store.start(job['id'],'other',claim['lease'],now=101)
        running=self.store.start(job['id'],'w',claim['lease'],now=101)
        before=running['deadline']
        heartbeat=self.store.heartbeat(job['id'],'w',claim['lease'],now=101.05)
        self.assertEqual(heartbeat['deadline'],before)
        with self.assertRaises(QueueError):self.store.heartbeat(job['id'],'w','wrong',now=101.05)
    def test_source_derived_wall_deadline_preserves_physical_duration(self):
        for sensor_source,expected_deadline in (('simulation',122.),('magnetic-step',112.)):
            with self.subTest(source=sensor_source):
                job=self.store.submit('alice',sensor_source,b'x','x.py',sensor_source,10.)
                claim=self.store.claim('w',sensor_source,now=100,sensor_source=sensor_source)
                started=self.store.start(job['id'],'w',claim['lease'],now=101)
                self.assertEqual(started['deadline'],expected_deadline)
                heartbeat=self.store.heartbeat(job['id'],'w',claim['lease'],now=101.1)
                self.assertEqual(heartbeat['deadline'],expected_deadline)

    def test_stale_running_blocks_rig_until_operator_recovery(self):
        job=self.submit();claim=self.store.claim('w','r',now=100)
        self.store.start(job['id'],'w',claim['lease'],now=101)
        self.store.recover(now=110)
        self.assertEqual(self.store.get(job['id'],'alice')['status'],'failed')
        self.submit(key='next')
        with self.assertRaises(QueueError):self.store.claim('w2','r',now=111)
        self.store.release_block('r',stopped_confirmed=True)
        self.assertIsNotNone(self.store.claim('w2','r',now=111))
    def test_cancel_active_requires_worker_stop_before_release(self):
        job=self.submit();claim=self.store.claim('w','r',now=100)
        self.store.start(job['id'],'w',claim['lease'],now=101)
        self.assertTrue(self.store.cancel(job['id'],'alice')['cancel_requested'])
        self.assertIsNone(self.store.claim('w2','r',now=101))
        self.store.finish(job['id'],'w',claim['lease'],'cancelled',{'stopped':True},now=101.05)
        self.submit(key='next');self.assertIsNotNone(self.store.claim('w2','r',now=101.06))
