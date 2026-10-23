import base64
import test_portal_http as base
from test_portal_artifacts import archive, SOURCE

class UploadHTTPTests(base.HTTPTests):
    def test_project_upload_and_inspection(self):
        payload=self.payload();payload.pop('source');payload.update(filename='project.zip',artifact_base64=base64.b64encode(archive([('policy.py',SOURCE),('helper.py',b'value=1')])).decode())
        status,job=self.request('/api/jobs',payload)
        assert status==201
        status,info=self.request('/api/jobs/'+job['id']+'/artifact',token='operator-secret-long')
        assert status==200 and info['kind']=='python-zip'
        assert info['filename']=='project.zip' and info['inspection']['entrypoint']=='policy.py'
        assert self.request('/api/jobs',payload|{'source':'x'})[0]==400
        assert self.request('/api/jobs',payload|{'artifact_base64':'%%%','idempotency_key':'bad'})[0]==400
