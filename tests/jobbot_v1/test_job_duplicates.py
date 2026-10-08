"""Synthetic semantic matching; no model server or employer is contacted."""
import json

import pytest

from job_applier.managed import ProtocolError
from test_local_sessions import setup


def pair(service, *, first_title='VP, Analytics', second_title='Vice President, Analytics',
         first_url='https://jobs.ashbyhq.com/example/aaaaaaaa-1111-2222-3333-444444444444',
         second_url='https://www.linkedin.com/jobs/view/1234567',
         first_company='Example, Inc.', second_company='Example', **metadata):
    facts={'location':'Chicago, IL', 'posted_at':'2026-10-01', **metadata}
    first=service.intake(url=first_url,company=first_company,title=first_title,**facts)
    second=service.intake(url=second_url,company=second_company,title=second_title,**facts)
    return first,second


def enable(service, mode='enforce'):
    service.configure({'duplicate_matching_mode':mode},expected_version=service.settings_view()['version'])


def success(service, job):
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?",(job['id'],))
        db.execute('INSERT INTO submission_ledger VALUES (?,?,?,?)',
                   (job['id'],'same-person','Synthetic employer confirmation',service.now()))


def test_successful_same_role_skips_and_is_audited_once_without_deleting_history(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service);success(service,first)
    for request in ('one','two'):
        with pytest.raises(ProtocolError,match='already_applied'):
            service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id=request)
    with service.read() as db:
        assert db.execute('SELECT count(*) FROM job_duplicate_skips WHERE job_id=?',(second['id'],)).fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM jobs WHERE id IN (?,?)',(first['id'],second['id'])).fetchone()[0]==2
        assert not db.execute('SELECT 1 FROM submission_ledger WHERE job_id=?',(second['id'],)).fetchone()


def test_failure_and_uncertain_history_still_retry(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service)
    with service.tx() as db:db.execute("UPDATE jobs SET status='submission_unknown' WHERE id=?",(first['id'],))
    result=service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='allowed')
    assert result['items'][0]['state']=='queued'


@pytest.mark.parametrize('overrides',[
    {'second_company':'Another Employer'},
    {'second_title':'Senior Vice President, Analytics'},
    {'first_url':'https://careers.example.test/jobs/100','second_url':'https://careers.example.test/jobs/200'},
])
def test_distinct_employer_seniority_and_native_requisition_are_not_suppressed(tmp_path,overrides):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service,**overrides);success(service,first)
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='distinct')['items']


def test_matching_title_alone_is_possible_not_confirmed(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service,location='',posted_at='');success(service,first)
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='unknown')['items']
    matches=service.duplicate_matches(job_id=second['id'])['matches']
    assert any(m['decision']=='possible' for m in matches)


def test_shadow_mode_and_operator_dismissal_do_not_suppress(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service,'shadow')
    first,second=pair(service);success(service,first)
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='shadow')['items']
    match=service.duplicate_matches(job_id=second['id'])['matches'][0]
    service.set_duplicate_match_state(match_id=match['id'],state='dismissed')
    enable(service)
    service.queue_reconcile(identity_id='candidate',resume_asset_id=asset['id'])
    assert service.queue_status()['latest_by_job'][second['id']]['state']=='queued'


def test_pending_queue_is_settled_but_active_request_is_preserved(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service)
    item=service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='pending')['items'][0]
    success(service,first)
    service.queue_reconcile(identity_id='candidate',resume_asset_id=asset['id'])
    assert service.queue_status()['latest_by_job'][second['id']]['outcome']=='already_applied'
    with service.tx() as db:db.execute("UPDATE dispatch_queue SET state='dispatched',outcome=NULL,ended_at=NULL WHERE id=?",(item['id'],))
    service.queue_reconcile(identity_id='candidate',resume_asset_id=asset['id'])
    assert service.queue_status()['latest_by_job'][second['id']]['state']=='dispatched'


def test_embedding_cache_and_outage_fallback(tmp_path):
    from job_applier.job_duplicates import DuplicateMatcher
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service,first_title='Head of Analytics',second_title='Analytics Head')
    calls=[]
    def embed(texts):
        calls.append(texts)
        return [[1.,0.,0.] for _ in texts]
    matcher=DuplicateMatcher(service,{'duplicate_matching':{'model':'fixture-v1'}},embed=embed)
    matcher.refresh();matcher.refresh()
    assert len(calls)==1
    success(service,first)
    with pytest.raises(ProtocolError,match='already_applied'):
        service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='semantic')
    first2,second2=pair(service,first_title='Director, Design',second_title='Design Director',
        first_url='https://example.test/design',second_url='https://other.example.test/design')
    success(service,first2)
    def unavailable(texts):raise TimeoutError('model unavailable')
    broken=DuplicateMatcher(service,{'duplicate_matching':{'model':'fixture-v2'}},embed=unavailable)
    assert broken.refresh()['embedding_status']=='unavailable'
    assert service.queue_enqueue(job_ids=[second2['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='continue')['items']


def test_changed_metadata_invalidates_previous_match(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service);success(service,first)
    service.duplicate_matches(job_id=second['id'])
    with service.tx() as db:db.execute("UPDATE jobs SET title='Vice President, Sales' WHERE id=?",(second['id'],))
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='changed')['items']


def test_matching_success_belongs_to_selected_candidate(tmp_path):
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service)
    service.identity(identity_id='other',person_key='other-person',email='other@example.test',profile={})
    with service.tx() as db:
        db.execute('INSERT INTO submission_ledger VALUES (?,?,?,?)',(first['id'],'other-person','Synthetic confirmation',service.now()))
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='different-person')['items']


def test_read_only_eligibility_checks_do_not_write_match_records(tmp_path):
    service,_,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service);success(service,first)
    with service.read() as db:
        with pytest.raises(ProtocolError,match='already_applied'):
            service._assert_not_suppressed(db,second['id'],identity_id='candidate')
        assert db.execute('SELECT count(*) FROM job_duplicate_matches').fetchone()[0]==0


@pytest.mark.parametrize('vector',[[float('nan'),1.],[float('inf'),1.],[0.,0.],[]])
def test_invalid_model_vectors_do_not_establish_duplicate(tmp_path,vector):
    from job_applier.job_duplicates import DuplicateMatcher
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service,first_title='Head of Analytics',second_title='Analytics Head');success(service,first)
    matcher=DuplicateMatcher(service,{'duplicate_matching':{'model':'invalid'}},embed=lambda texts:[vector for _ in texts])
    assert matcher.refresh()['embedding_status']=='unavailable'
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='still-eligible')['items']


def test_conflicting_native_ids_override_perfect_embeddings(tmp_path):
    from job_applier.job_duplicates import DuplicateMatcher
    service,asset,_,_,_=setup(tmp_path);enable(service)
    first,second=pair(service,first_url='https://careers.example.test/jobs/100',second_url='https://careers.example.test/jobs/200')
    success(service,first)
    DuplicateMatcher(service,{'duplicate_matching':{'model':'fixture'}},embed=lambda texts:[[1.,0.] for _ in texts]).refresh()
    assert service.queue_enqueue(job_ids=[second['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='conflict')['items']


def test_operator_can_review_matches_but_worker_cannot_dismiss_them(tmp_path):
    from fastapi.testclient import TestClient
    from job_applier.managed_api import create_app
    service,_,_,_,_=setup(tmp_path);first,second=pair(service)
    operator='o'*32;worker='w'*32
    client=TestClient(create_app(service,operator_token=operator,worker_tokens={worker:'fixture-worker'}),base_url='http://127.0.0.1')
    headers={'Authorization':'Bearer '+operator,'X-JobBot-Instance':service.instance_id}
    response=client.post('/v1/duplicate_matches',json={'job_id':second['id']},headers=headers)
    assert response.status_code==200
    match=response.json()['matches'][0]
    payload={'match_id':match['id'],'state':'dismissed'}
    assert client.post('/v1/set_duplicate_match_state',json=payload,headers=headers|{'Authorization':'Bearer '+worker}).status_code==403
    assert client.post('/v1/set_duplicate_match_state',json=payload,headers=headers).status_code==200


def test_dashboard_explains_match_and_sends_explicit_dismissal():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
v.jobs=[{id:'new',seq_id:2,company:'Example',title:'Director, Analytics',status:'queued',duplicate_matches:[
 {id:'match',other_seq_id:1,decision:'confirmed',operator_state:'automatic',evidence:['Same location and posting date']}]}];
w.draw(v);w.noRefresh();let calls=[];
w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:true,status:200,json:async()=>({})};};
const details=doc.querySelector('.job-duplicate');
assert(details.textContent.includes('Matching posting'),'Match classification missing');
assert(details.textContent.includes('Same location and posting date'),'Matching evidence missing');
await [...details.querySelectorAll('button')].find(b=>b.textContent==='These are different jobs').onclick();
assert(calls[0][0]==='/v1/set_duplicate_match_state','Wrong dismissal operation');
assert(calls[0][1].match_id==='match'&&calls[0][1].state==='dismissed','Wrong match dismissed');
''')
