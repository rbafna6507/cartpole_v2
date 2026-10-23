"""Physical execution requires a separate operator decision on immutable inputs."""
import sqlite3
import tempfile
import unittest
from cartpole_sdk.portal.queue import Store, QueueError
from test_portal_http import HTTPTests

class ApprovalQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def submit(self, source='magnetic-step', key='one'):
        return self.store.submit('alice',key,b'x=1','policy.py',source,1.)
    def approve(self, job, **changes):
        review = dict(artifact=job['artifact'], sensor_source=job['source'], duration=job['duration'])
        review.update(changes)
        return self.store.approve(job['id'],'operator',**review)
    def test_hardware_waits_for_exact_review_and_persists_approval(self):
        job=self.submit()
        self.assertEqual(job['status'],'awaiting_approval')
        self.assertIsNone(self.store.claim('worker','rig'))
        for changes in ({'artifact':'0'*64},{'duration':2.},{'sensor_source':'simulation'}):
            with self.assertRaises(QueueError):self.approve(job,**changes)
        approved=self.approve(job)
        self.assertEqual(approved['approved_by'],'operator')
        self.assertIsNotNone(approved['approved_at'])
        self.assertEqual(Store(self.tmp.name).claim('worker','rig')['id'],job['id'])
        with self.assertRaises(QueueError):self.approve(job)
    def test_simulation_needs_no_approval(self):
        job=self.submit('simulation')
        self.assertEqual(self.store.claim('worker','sim')['id'],job['id'])
    def test_waiting_cancellation_and_quota(self):
        first=self.submit()
        for n in range(31):self.submit(key=f'job{n}')
        with self.assertRaises(QueueError):self.submit(key='overflow')
        self.assertEqual(self.store.cancel(first['id'],'alice')['status'],'cancelled')
        with self.assertRaises(QueueError):self.approve(first)
        self.submit(key='replacement')
    def test_legacy_pending_physical_job_cannot_skip_approval(self):
        job=self.submit()
        with sqlite3.connect(self.store.database) as db:
            db.execute("UPDATE jobs SET status='pending' WHERE id=?",(job['id'],))
        reopened=Store(self.tmp.name)
        self.assertEqual(reopened.get(job['id'])['status'],'awaiting_approval')
        self.assertIsNone(reopened.claim('worker','rig'))

    def test_repeated_approval_preserves_first_receipt(self):
        job=self.submit()
        first=self.approve(job)
        again=self.store.approve(job['id'],'another-operator',artifact=job['artifact'],sensor_source=job['source'],duration=job['duration'])
        self.assertEqual((first['approved_by'],first['approved_at']),(again['approved_by'],again['approved_at']))

    def test_legacy_schema_migration_preserves_active_lease(self):
        pending=self.submit()
        active=self.submit(key='active')
        self.approve(active)
        claim=self.store.claim('worker','rig')
        with sqlite3.connect(self.store.database) as db:
            db.execute("UPDATE jobs SET status='pending' WHERE id=?",(pending['id'],))
            db.execute('ALTER TABLE jobs DROP COLUMN approved_by')
            db.execute('ALTER TABLE jobs DROP COLUMN approved_at')
        reopened=Store(self.tmp.name)
        self.assertEqual(reopened.get(pending['id'])['status'],'awaiting_approval')
        self.assertEqual(reopened.get(active['id'])['status'],'claimed')
        with sqlite3.connect(reopened.database) as db:
            self.assertEqual(db.execute('SELECT lease FROM jobs WHERE id=?',(active['id'],)).fetchone()[0],claim['lease'])

class ApprovalHTTPTests(HTTPTests):
    def test_only_operator_can_approve_reviewed_hardware_job(self):
        job=self.request('/api/jobs',self.payload())[1]
        path='/api/jobs/'+job['id']+'/approve'
        review=dict(artifact=job['artifact'],sensor_source=job['source'],duration=job['duration'])
        for token in ('alice-secret-long','worker-secret-long'):
            self.assertEqual(self.request(path,review,token=token)[0],403)
        self.assertEqual(self.request(path,review|{'duration':2},token='operator-secret-long')[0],400)
        self.assertIsNone(self.request('/api/claim',{'rig':'r'},token='worker-secret-long')[1]['job'])
        self.assertEqual(self.request(path,review,token='operator-secret-long')[0],200)
        self.assertEqual(self.request('/api/claim',{'rig':'r'},token='worker-secret-long')[1]['job']['id'],job['id'])

    def test_operator_can_inspect_source_before_approving(self):
        import base64
        job=self.request('/api/jobs',self.payload())[1]
        path='/api/jobs/'+job['id']+'/artifact'
        code,data=self.request(path,token='operator-secret-long')
        self.assertEqual(code,200)
        self.assertEqual(base64.b64decode(data['source_base64']).decode(),self.payload()['source'])
        self.assertEqual(data['sha256'],job['artifact'])
        self.assertEqual(self.request(path,token='bob-secret-long')[0],403)
        self.assertEqual(self.request(path,token='worker-secret-long')[0],404)
