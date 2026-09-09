"""Synthetic full managed protocol path; actual service/DB, no employer or account."""
import asyncio
import hashlib
import os
import sys
from contextlib import nullcontext
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from job_applier.managed import Service
from job_applier.managed_api import create_app
from job_applier.cdp_client import CDPBrowser
from job_applier.workday_fast import FastRunner, WORKDAY_OBSERVE
from job_applier.simplify_boundary import OBSERVE,CLICK
from job_applier.submission import SCRIPT as SUBMISSION_OBSERVE


@pytest.mark.parametrize('panel_after',[True,False])
@pytest.mark.parametrize('transport',['http','local'])
def test_fast_runner_finishes_through_real_managed_api(tmp_path,monkeypatch,panel_after,transport):
    s=Service.create(tmp_path/'fixture.db',instance_id='fixture-fast',settings={'mode':'pilot','submission_mode':'submit'})
    s.identity(identity_id='fixture-person',person_key='fixture-person',email='fixture@example.test',profile={})
    asset=s.register_asset(identity_id='fixture-person',kind='resume',version='fixture-1',sha256=hashlib.sha256(b'synthetic fixture').hexdigest(),provenance={'source':'synthetic'},storage_ref=(tmp_path/'fixture.pdf').as_uri())
    url='https://fixture.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1'
    job=s.intake(url=url,source_id='fixture',company='Synthetic Fixture')
    s.eligibility(job['id'],'ready',reason='synthetic test')
    s.select_asset(asset_id=asset['id'],job_id=job['id'])
    if transport=='local':
        from job_applier.workspace_process import process_identity
        s.configure_workspaces([{'id':'fixture-browser','user_data_dir':str(tmp_path/'profile'),'browser_executable':sys.executable,'cdp_url':'http://127.0.0.1:9223','mode':'headed'}])
        session=s.reserve_session(request_id='fixture-run',job_id=job['id'],identity_id='fixture-person',driver_id='fixture-session',workspace_ids=['fixture-browser'],concurrency_limit=1,resume_asset_id=asset['id'])
        s.host_registered('fixture-browser','fixture-host',process_identity(os.getpid()))
        session=s.session_connected(session['id'],'fixture-host','fixture-tab',{'synthetic':True})
        attempt=s.attempt(session['attempt_id'])
    else:
        run=s.request_run(request_id='fixture-run',job_ids=[job['id']],identity_id='fixture-person',browser_profile='fixture-browser')
        s.accept_run(run['id'],worker_id='fixture-worker',session_id='fixture-session',capabilities={'protocol':1,'skill_version':'fixture','browser_profile':'fixture-browser','provider':'fixture','model':'fixture','telemetry':True})
        attempt=s.claim(run['id'],worker_id='fixture-worker')
    owner={'attempt_id':attempt['id'],'worker_id':attempt['worker_id'],'fence':attempt['fence']}
    s.bind_target(**owner,target_id='fixture-tab',url=url)
    class Page:
        index=0
        class Session:
            def subscribe(self,*args):return lambda:None
            async def call(self,*args,**kwargs):return {'identifier':'synthetic-new-document-hook'}
        _session=Session()
        async def evaluate(self,expression):
            if expression=='location.href':return url if self.index<2 else 'https://fixture.wd1.myworkdayjobs.com/en-US/Jobs/candidateHome'
            assert expression==OBSERVE
            return {'url':url,'status':'complete' if self.index<2 or panel_after else 'missing','panel':self.index<2 or panel_after,'fingerprint':str(self.index),'page_signature':str(self.index),'page_ref':'fixture-page','source':'observed_dom','controls':{'continue' if self.index==0 else 'submit':{'ref':'observed','enabled':True}}}
        async def evaluate_function(self,expression,args):
            if expression==WORKDAY_OBSERVE:
                return {'step':['my_experience','review','unknown'][self.index],'native':{},'auth':False,'blocking_errors':[],
                        'resume_attached':True,'submitted':self.index==2,'identity_mismatch':False}
            if expression==SUBMISSION_OBSERVE:
                if args.get('operation')=='read':
                    return [{'source':'employer','text':'Thank you for applying','url':await self.evaluate('location.href')} ] if self.index==2 else []
                return {'baseline':[]}
            if expression==CLICK:
                self.index+=1;return {'status':'clicked'}
            return {'answers':[]}
    page=Page()
    browser=type('Browser',(),{'get_current_page':AsyncMock(return_value=page),'close':AsyncMock(),'observed_mode':'headed'})()
    monkeypatch.setattr(CDPBrowser,'connect',AsyncMock(return_value=browser))
    # The real browser/masking paths have separate isolated-browser coverage.
    monkeypatch.setattr('job_applier.managed_credentials.capture_private_screenshot',AsyncMock())
    token='synthetic-fixture-worker-token-32chars'
    with (nullcontext() if transport=='local' else TestClient(create_app(s,operator_token='synthetic-fixture-operator-token-32chars',worker_tokens={token:'fixture-worker'}),base_url='http://127.0.0.1:8769')) as api:
        def call(op,**payload):
            if transport=='local':
                from job_applier.managed_client import LocalClient
                return LocalClient({'db_path':str(s.db_path),'instance_id':s.instance_id},service=s).call(op,**payload)
            response=api.post('/v1/'+op,headers={'Authorization':'Bearer '+token,'X-JobBot-Instance':s.instance_id},json=payload)
            assert response.status_code==200,(op,response.status_code,response.text)
            return response.json()
        package=call('application_context',attempt_id=attempt['id'],worker_id=owner['worker_id'])
        runner=FastRunner(page,call,package,owner,{'cdp_url':'http://127.0.0.1:9223','spool_dir':str(tmp_path/'spool')},'fixture-tab')
        result=asyncio.run(runner.run(seconds=8))
    assert result['status']=='applied'
    assert s.attempt(attempt['id'])['outcome']=='applied'
    assert s.job(job['id'])['status']=='applied'
    assert s.attempt(attempt['id'])['submit_intent_at']
    assert s.documents_status(job['id'],identity_id='fixture-person',attempt_id=attempt['id'])['ready'] is True


def test_known_idle_account_control_settles_start_application_writer(tmp_path,monkeypatch):
    from test_product_integration import make_service_with_attempt, WORKER_ID
    url='https://fixture.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1'
    service,job,run,attempt=make_service_with_attempt(tmp_path,url=url)
    owner={'attempt_id':attempt['id'],'worker_id':WORKER_ID,'fence':attempt['fence']}
    service.bind_target(**owner,target_id='account-tab',url=url)
    service.writer_state(**owner,state='active')
    class Page:
        async def evaluate(self,expression):
            if expression=='location.href':return url+'/apply'
            return {'url':url+'/apply','status':'login_required','panel':True,'fingerprint':'settled','page_signature':'account','page_ref':'account',
                    'source':'observed_dom','controls':{'create_account_autofill':{'enabled':True,'ref':'account-control'}}}
    browser=type('Browser',(),{'get_current_page':AsyncMock(return_value=Page()),'close':AsyncMock(),'observed_mode':'headed'})()
    monkeypatch.setattr(CDPBrowser,'connect',AsyncMock(return_value=browser))
    observed=service.browser_observe(**owner,target_id='account-tab',cdp_url='http://127.0.0.1:9223')
    assert observed['quiescent'] is True
    assert service.attempt(attempt['id'])['writer_state']=='idle'
