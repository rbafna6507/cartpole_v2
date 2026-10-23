import test_portal_http as base


class WorkspaceHTTPTests(base.HTTPTests):
    def test_config_requires_auth_and_reservations_disabled(self):
        assert self.request('/api/config',token='bad')[0]==401
        code,config=self.request('/api/config')
        assert code==200 and config['reservations_enabled'] is False
        assert self.request('/api/reservations',dict(rig='cartpole',starts_at=1,duration_minutes=30))[0]==400

    def test_reservation_api_owner_and_optional_job_binding(self):
        import time
        self.store.reservations_enabled=True
        code,r=self.request('/api/reservations',dict(rig='cartpole',starts_at=time.time(),duration_minutes=30))
        assert code==201
        assert self.request('/api/reservations',token='bob-secret-long')[1]['reservations']==[]
        payload=self.payload()|{'reservation_id':r['id']}
        assert self.request('/api/jobs',payload)[0]==201
        assert self.request('/api/reservations/'+r['id']+'/cancel',{},token='bob-secret-long')[0] in (400,404)
        assert self.request('/api/reservations/'+r['id']+'/cancel',{})[1]['status']=='cancelled'

    def test_recording_download_roles(self):
        job=self.request('/api/jobs',self.payload())[1]
        path='/api/jobs/'+job['id']+'/recording'
        assert self.request(path,token='bob-secret-long')[0]==404
        assert self.request(path,token='worker-secret-long')[0]==403
        assert self.request(path)[0]==404
