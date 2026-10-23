"""Real loopback HTTP ownership/auth/body/origin boundaries."""
import json
import tempfile
import socket
import time
import threading
import unittest
import urllib.error
import urllib.request
from cartpole_sdk.portal.queue import Store
from cartpole_sdk.portal.server import make_server

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.server=make_server(self.store,{'alice-secret-long':('alice','submit'),'bob-secret-long':('bob','submit'),'worker-secret-long':('worker','worker'),'operator-secret-long':('operator','operator')},port=0)
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,token='alice-secret-long',origin=None):
        headers={'Authorization':'Bearer '+token}
        if origin:headers['Origin']=origin
        if body is not None:headers['Content-Type']='application/json'
        request=urllib.request.Request(self.origin+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=2) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as response:return response.code,json.loads(response.read())
    def payload(self):return dict(source='def create_policy():\n return None\n',filename='test.py',sensor_source='magnetic-step',duration=.1,idempotency_key='one')
    def test_auth_and_role_guards(self):
        self.assertEqual(self.request('/api/jobs',token='bad')[0],401)
        self.assertEqual(self.request('/api/claim',{'rig':'r'},token='alice-secret-long')[0],403)
        self.assertEqual(self.request('/api/jobs',self.payload(),token='worker-secret-long')[0],403)
    def test_submit_list_ownership_and_result(self):
        code,job=self.request('/api/jobs',self.payload());self.assertEqual(code,201)
        self.assertEqual(self.request('/api/jobs/'+job['id'],token='bob-secret-long')[0],404)
        self.assertEqual(len(self.request('/api/jobs')[1]['jobs']),1)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/cancel',{})[1]['status'],'cancelled')
    def test_cross_origin_browser_mutation_rejected(self):
        self.assertEqual(self.request('/api/jobs',self.payload(),origin='http://evil.example')[0],403)
        self.assertEqual(self.request('/api/jobs',self.payload(),origin=self.origin)[0],201)
    def test_source_size_unknown_fields_and_path_rejected(self):
        for payload in (self.payload()|{'source':'x'*65537},self.payload()|{'extra':'x'},self.payload()|{'max_acceleration':25},self.payload()|{'wall_seconds':1000},self.payload()|{'filename':'../../etc.py'}):
            self.assertEqual(self.request('/api/jobs',payload)[0],400)
        self.assertEqual(self.request('/api/jobs/../../etc')[0],404)
    def test_worker_claim_fetch_and_reset_before_start_contract(self):
        job=self.request('/api/jobs',self.payload())[1]
        self.request('/api/jobs/'+job['id']+'/approve',dict(artifact=job['artifact'],sensor_source=job['source'],duration=job['duration']),token='operator-secret-long')
        claim=self.request('/api/claim',{'rig':'r'},token='worker-secret-long')[1]['job']
        self.assertEqual(claim['id'],job['id']);self.assertIn('lease',claim)
        self.assertNotIn('lease',self.request('/api/jobs/'+job['id'])[1])
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/artifact',token='alice-secret-long')[0],403)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/artifact',token='worker-secret-long')[1]['sha256'],job['artifact'])
    def test_slow_body_progress_cannot_extend_absolute_request_budget(self):
        self.server.request_timeout=.15
        with socket.create_connection(('127.0.0.1',self.server.server_port),timeout=.5) as client:
            began=time.monotonic()
            client.sendall(b'POST /api/jobs HTTP/1.0\r\nAuthorization: Bearer alice-secret-long\r\nContent-Type: application/json\r\nContent-Length: 5\r\n\r\n{')
            time.sleep(.09);client.sendall(b'"')
            reply=client.recv(4096)
            self.assertIn(b'408',reply)
            self.assertLess(time.monotonic()-began,.3)

    def test_ui_is_public_but_does_not_embed_credentials(self):
        with urllib.request.urlopen(self.origin+'/',timeout=2) as response:
            html=response.read().decode();self.assertIn('New experiment',html);self.assertNotIn('alice-secret-long',html)
            self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
