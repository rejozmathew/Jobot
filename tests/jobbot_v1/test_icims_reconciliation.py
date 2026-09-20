"""Manual completion keeps truthful evidence and settles only queued duplicates."""
import pytest

from job_applier.managed_shared import ProtocolError,uid
from test_local_sessions import setup,reserve,connect,own
from test_dispatch_queue import enqueue


def test_manual_completion_preserves_stop_and_other_jobs_and_identities(tmp_path):
    s,asset,jobs,_,_=setup(tmp_path)
    session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    queued=enqueue(s,asset,[jobs[0],jobs[1]])['items']
    s.identity(identity_id='another',person_key='another-person',email='another@example.test',profile={})
    with s.tx() as db:
        for identity,state in [('another','queued'),('candidate','dispatched')]:
            key=uid()
            db.execute('INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at) VALUES (?,?,?,?,?,?,?)',
                (key,key,jobs[2]['id'] if state=='dispatched' else jobs[0]['id'],identity,asset['id'],state,s.now()))
    with pytest.raises(ProtocolError,match='local_session_stop_required'):
        s.reconcile(session['attempt_id'],outcome='applied',evidence='Operator finished',source='user_reported',browser_quiescent=True)
    s.session_stopped(session['id'],reason='stop_requested',browser_stopped=True)
    stop=s.session(session['id'])['ended_at']
    result=s.reconcile(session['attempt_id'],outcome='applied',evidence='Operator finished',source='user_reported',browser_quiescent=True)
    assert result['submit_intent_at'] is None
    assert s.session(session['id'])['ended_at']==stop
    with s.tx() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM dispatch_queue')]
        settled=next(r for r in rows if r['id']==queued[0]['id'])
        assert settled['state']=='finished' and settled['outcome']=='already_applied' and 'reconciliation' in settled['detail']
        assert next(r for r in rows if r['id']==queued[1]['id'])['state']=='queued'
        assert next(r for r in rows if r['identity_id']=='another')['state']=='queued'
        assert any(r['state']=='dispatched' for r in rows)
        # Repeated reconciliation also cleans a stale queued success row.
        db.execute("UPDATE dispatch_queue SET state='queued',ended_at=NULL WHERE id=?",(queued[0]['id'],))
    s.reconcile(session['attempt_id'],outcome='applied',evidence='Operator finished',source='user_reported',browser_quiescent=True)
    with s.tx() as db:assert db.execute('SELECT state FROM dispatch_queue WHERE id=?',(queued[0]['id'],)).fetchone()[0]=='finished'
    report=s.attempt_report(session['attempt_id'])
    assert any(e.get('payload',{}).get('source')=='user_reported' for e in report['timeline'])


def test_newer_attempt_guard_still_precedes_reconcile_cleanup(tmp_path):
    s,asset,jobs,_,_=setup(tmp_path)
    first=connect(s,reserve(s,asset,jobs));s.session_stopped(first['id'],reason='stop_requested',browser_stopped=True)
    second=connect(s,reserve(s,asset,jobs,request='new-request',driver='new-driver'))
    with pytest.raises(ProtocolError,match='newer_attempt_exists'):
        s.reconcile(first['attempt_id'],outcome='applied',evidence='Late operator report',source='user_reported',browser_quiescent=True)
    assert not s.session(second['id'])['ended_at']


def test_reconcile_serializes_queue_take_and_preserves_dispatched(tmp_path,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    s,asset,jobs,_,_=setup(tmp_path)
    session=connect(s,reserve(s,asset,jobs));s.session_stopped(session['id'],reason='stop_requested',browser_stopped=True)
    item=enqueue(s,asset,[jobs[0]])['items'][0]
    entered=threading.Event();release=threading.Event();original=s._settle_reconciled_queue
    def settle(db,attempt):
        entered.set();assert release.wait(5)
        return original(db,attempt)
    monkeypatch.setattr(s,'_settle_reconciled_queue',settle)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reconcile=pool.submit(s.reconcile,session['attempt_id'],outcome='applied',evidence='Operator finished',source='user_reported',browser_quiescent=True)
        assert entered.wait(5)
        take=pool.submit(s.queue_take);release.set();reconcile.result()
        assert take.result() is None
    with s.tx() as db:
        assert db.execute('SELECT state FROM dispatch_queue WHERE id=?',(item['id'],)).fetchone()[0]=='finished'
        db.execute("UPDATE dispatch_queue SET state='dispatched',outcome=NULL,ended_at=NULL WHERE id=?",(item['id'],))
    # Idempotent success cleanup never rewrites an already dispatched executor.
    s.reconcile(session['attempt_id'],outcome='applied',evidence='Operator finished',source='user_reported',browser_quiescent=True)
    with s.tx() as db:assert db.execute('SELECT state FROM dispatch_queue WHERE id=?',(item['id'],)).fetchone()[0]=='dispatched'
