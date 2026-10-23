import io
import threading
import urllib.request
import urllib.error
import zipfile
import pytest
from cartpole_sdk.portal.queue import Store
from cartpole_sdk.portal.server import make_server
from cartpole_sdk.portal.worker import RemoteQueue, run_once
from test_portal_worker import TrustedPipeFixture


def test_remote_worker_upload_and_owner_download(tmp_path):
    store=Store(tmp_path/'store')
    job=store.submit('alice','one',b'x','x.py','simulation',.1)
    server=make_server(store,{'worker-secret-long':('w','worker'),'alice-secret-long':('alice','submit'),'bob-secret-long':('bob','submit')},port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    try:
        result=run_once(RemoteQueue(origin,'worker-secret-long'),'w','sim',sandbox_factory=TrustedPipeFixture,recording_root=tmp_path/'spool')
        assert result['result']['recording']['status']=='available'
        url=origin+'/api/jobs/'+job['id']+'/recording'
        request=urllib.request.Request(url,headers={'Authorization':'Bearer alice-secret-long'})
        with urllib.request.urlopen(request) as response:
            assert response.headers['Content-Type']=='application/zip'
            assert set(zipfile.ZipFile(io.BytesIO(response.read())).namelist())=={'manifest.json','telemetry.jsonl'}
        request=urllib.request.Request(url,headers={'Authorization':'Bearer bob-secret-long'})
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        assert error.value.code==404
    finally:server.shutdown();server.server_close();thread.join()
