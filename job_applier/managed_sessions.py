"""Local session records in the existing managed database, shared by both transports.

Browser I/O belongs to the workspace host, outside these short transactions.
Legacy leases remain for explicit compatibility runs, never for local sessions.
"""
import hashlib
import json
from datetime import datetime

from .managed_identity import RELATED
from .managed_redaction import reject_secrets, safe_text
from .managed_shared import ProtocolError, dumps, uid


def local_session(db, attempt_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='application_sessions'").fetchone():
        return None
    return db.execute('SELECT * FROM application_sessions WHERE attempt_id=?', (attempt_id,)).fetchone()


class SessionServices:
    @staticmethod
    def _has_local_schema(db):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='application_sessions'").fetchone())

    def configure_workspaces(self, workspaces):
        """Called from the selected private config; identities/paths are immutable while occupied."""
        from .application_runtime import validate_workspaces
        workspaces=validate_workspaces(workspaces)
        with self.tx() as db:
            for workspace in workspaces:
                encoded=dumps(workspace)
                old=db.execute('SELECT * FROM browser_workspaces WHERE id=?',(workspace['id'],)).fetchone()
                if old and old['config_json']!=encoded:
                    if old['state']!='offline' or db.execute('SELECT 1 FROM application_sessions WHERE workspace_id=? AND ended_at IS NULL',(workspace['id'],)).fetchone():
                        raise ProtocolError('workspace_configuration_in_use')
                db.execute('''INSERT INTO browser_workspaces(id,config_json,updated_at) VALUES (?,?,?)
                    ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at''',
                    (workspace['id'],encoded,self.now()))
                for profile in [workspace['id'],*workspace.get('legacy_profiles',[])]:
                    alias=db.execute('SELECT workspace_id FROM workspace_profile_aliases WHERE profile=?',(profile,)).fetchone()
                    if alias and alias[0]!=workspace['id']:raise ProtocolError('workspace_alias_conflict')
                    db.execute('INSERT OR IGNORE INTO workspace_profile_aliases VALUES (?,?)',(profile,workspace['id']))
        return workspaces

    def reserve_session(self, *, request_id, job_id, identity_id, driver_id, workspace_ids,
                        concurrency_limit, metadata=None, resume_asset_id=None):
        if not request_id or not driver_id or not workspace_ids:
            raise ProtocolError('local_request_context_required')
        reject_secrets(metadata or {})
        key=dumps([job_id,identity_id,driver_id,resume_asset_id])
        with self.tx() as db:
            old=db.execute('SELECT * FROM application_sessions WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['request_key']!=key:raise ProtocolError('idempotency_conflict')
                if old['state']!='capacity_wait':return dict(old)
            else:
                active=db.execute(RELATED+'''SELECT s.* FROM related r JOIN application_sessions s ON s.job_id=r.id
                    WHERE s.ended_at IS NULL LIMIT 1''',(job_id,)).fetchone()
                if active:
                    if active['driver_id']==driver_id and active['identity_id']==identity_id:
                        return dict(active)
                    raise ProtocolError('owned_elsewhere')
            settings=self._settings_record(db)['values']
            self._eligible(db,job_id,settings,old['id'] if old else None)
            candidate=self._get(db,'candidates',identity_id)
            if candidate['state']!='active':raise ProtocolError('identity_inactive')
            if not resume_asset_id:raise ProtocolError('configured_resume_required')
            asset=self._get(db,'document_assets',resume_asset_id)
            if asset['identity_id']!=identity_id or asset['kind']!='resume' or asset['status']!='available':
                raise ProtocolError('asset_identity_mismatch')
            occupied=db.execute('SELECT workspace_id FROM application_sessions WHERE workspace_id IS NOT NULL AND ended_at IS NULL').fetchall()
            taken={x[0] for x in occupied}
            selected=None
            if len(taken)<concurrency_limit:
                for wid in workspace_ids:
                    w=self._get(db,'browser_workspaces',wid)
                    if wid not in taken and w['state'] not in ('failed','isolating'):
                        lease=db.execute("SELECT 1 FROM browser_leases l JOIN workspace_profile_aliases a ON a.profile=l.profile WHERE a.workspace_id=? AND l.state!='released'",(wid,)).fetchone()
                        if not lease:selected=wid;break
            now=self.now();sid=old['id'] if old else uid()
            state='preparing' if selected else 'capacity_wait'
            reason=None if selected else 'Configured workspaces are occupied or unavailable'
            if old:
                db.execute('UPDATE application_sessions SET workspace_id=?,state=?,reason=?,preparing_at=? WHERE id=?',
                           (selected,state,reason,now if selected else None,sid))
            else:
                session_metadata=dict(metadata or {})
                # A new conversation/request can retry the same job without using
                # the retry command. Derive cleanup from history, not driver IDs.
                session_metadata['fresh_employer_storage']=bool(db.execute(RELATED+'''SELECT 1 FROM related r
                    WHERE EXISTS (SELECT 1 FROM application_attempts a WHERE a.job_id=r.id)
                       OR EXISTS (SELECT 1 FROM application_sessions s WHERE s.job_id=r.id AND s.ended_at IS NOT NULL)
                    LIMIT 1''',(job_id,)).fetchone())
                db.execute('''INSERT INTO application_sessions(id,request_id,request_key,job_id,identity_id,
                    driver_id,workspace_id,state,reason,requested_at,preparing_at,driver_seen_at,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (sid,request_id,key,job_id,identity_id,driver_id,selected,state,reason,now,now if selected else None,now,dumps(session_metadata)))
            if selected:
                run_id=uid();snapshot=dict(settings)
                # Startup/model gaps are telemetry, not an authorization expiry.
                # The host enforces optional maximum_runtime_seconds by stopping its child.
                snapshot['ownership_mode']='local-session-v1'
                snapshot['browser_mode']=json.loads(self._get(db,'browser_workspaces',selected)['config_json']).get('mode','headed')
                versions=dict(metadata or {},protocol=2,transport='local',browser_profile=selected)
                db.execute('''INSERT INTO runs(id,request_id,request_key,identity_id,browser_profile,state,
                    requested_at,worker_id,session_id,settings_json,capabilities_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (run_id,'local:'+sid,key,identity_id,selected,'preparing',now,'local:'+sid,driver_id,dumps(snapshot),dumps(versions)))
                db.execute('INSERT INTO run_jobs(run_id,job_id,position) VALUES (?,?,0)',(run_id,job_id))
                db.execute('UPDATE application_sessions SET run_id=? WHERE id=?',(run_id,sid))
                # Freeze the explicitly approved asset for this request. No file hunting.
                db.execute('INSERT INTO document_selections VALUES (?,?,?,?,?,?)',
                           (uid(),resume_asset_id,job_id,None,'selected',now))
            return dict(self._get(db,'application_sessions',sid))

    def session(self, session_id):
        with self.tx() as db:return dict(self._get(db,'application_sessions',session_id))

    def session_human_input(self,session_id,driver_id,capabilities):
        """Record the attached harness's observed messaging availability, not browser authority."""
        from .managed_questions import human_input_capabilities
        normalized=human_input_capabilities({'human_input':capabilities})
        with self.tx() as db:
            session=self._get(db,'application_sessions',session_id)
            if session['driver_id']!=driver_id or session['ended_at']:raise ProtocolError('driver_owned_elsewhere')
            metadata=json.loads(session['metadata_json'])
            if metadata.get('human_input')!=normalized:
                metadata['human_input']=normalized
                db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',(dumps(metadata),session_id))
        return normalized

    def session_status(self, session_id):
        with self.tx() as db:
            s=dict(self._get(db,'application_sessions',session_id))
            workspace=dict(self._get(db,'browser_workspaces',s['workspace_id'])) if s['workspace_id'] else None
            attempt=dict(self._get(db,'application_attempts',s['attempt_id'])) if s['attempt_id'] else None
            steps=[{**dict(row),'payload':json.loads(row['payload_json'])} for row in db.execute(
                "SELECT event_type,observed_at,payload_json FROM managed_events WHERE attempt_id=? AND stale=0 AND event_type IN ('phase_changed','navigation_verified','account_verified','recovery','outcome') ORDER BY recorded_at DESC,id DESC LIMIT 12",
                (s['attempt_id'],))] if attempt else []
            for step in steps:step.pop('payload_json')
        from .workspace_process import process_matches
        host_alive=bool(workspace and workspace['host_identity_json'] and process_matches(json.loads(workspace['host_identity_json'])))
        now=datetime.fromisoformat(self.now())
        def age(value):return max(0,(now-datetime.fromisoformat(value)).total_seconds()) if value else None
        cfg=json.loads(workspace['config_json']) if workspace else None
        return {**s,'transport':'local','workspace':cfg,'host_alive':host_alive,
                'activity':steps[0] if steps else None,'steps':list(reversed(steps)),
                'host_seen_at':workspace['host_seen_at'] if workspace else None,
                'driver_age_seconds':age(s['driver_seen_at']),
                'driver_recently_active':age(s['driver_seen_at']) is not None and age(s['driver_seen_at'])<120,
                'last_verified_progress_at':attempt['progress_at'] if attempt else None,
                'writer_state':attempt['writer_state'] if attempt else 'unknown',
                'elapsed_seconds':age(s['requested_at']) if not s['ended_at'] else max(0,(datetime.fromisoformat(s['ended_at'])-datetime.fromisoformat(s['requested_at'])).total_seconds()),
                'queue_seconds':max(0,(datetime.fromisoformat(s['preparing_at'] or self.now())-datetime.fromisoformat(s['requested_at'])).total_seconds()),
                'startup_seconds':max(0,(datetime.fromisoformat(s['connected_at'] or s['ended_at'] or self.now())-datetime.fromisoformat(s['preparing_at'])).total_seconds()) if s['preparing_at'] else None,
                'metadata':json.loads(s['metadata_json'])}

    def _local_owner(self, db, session):
        """Only the assigned host executing for the attached driver can write."""
        authority=getattr(self,'session_authority',None)
        w=self._get(db,'browser_workspaces',session['workspace_id'])
        if authority!=(session['id'],session['driver_id'],w['host_id']):
            raise ProtocolError('local_session_transport_required')
        if session['ended_at'] or session['state'] not in ('connected','waiting'):
            raise ProtocolError('local_session_not_connected')

    def _legacy_workspace_guard(self,db,profile):
        if self._has_local_schema(db) and db.execute('SELECT 1 FROM workspace_profile_aliases WHERE profile=?',(profile,)).fetchone():
            raise ProtocolError('local_workspace_requires_session')

    def host_registered(self, workspace_id, host_id, identity):
        with self.tx() as db:
            self._get(db,'browser_workspaces',workspace_id)
            db.execute("UPDATE browser_workspaces SET host_id=?,host_identity_json=?,host_seen_at=?,state='ready',reason=NULL,updated_at=? WHERE id=?",
                       (host_id,dumps(identity),self.now(),self.now(),workspace_id))

    def host_seen(self, workspace_id, host_id, browser_identity=None):
        with self.tx() as db:
            if self._get(db,'browser_workspaces',workspace_id)['host_id']!=host_id:raise ProtocolError('stale_host')
            db.execute('UPDATE browser_workspaces SET host_seen_at=?,browser_identity_json=?,updated_at=? WHERE id=?',
                       (self.now(),dumps(browser_identity) if browser_identity else None,self.now(),workspace_id))

    def session_connected(self, session_id, host_id, target_id, readiness):
        """Readiness is produced by the host. Claim happens only AFTER real browser I/O."""
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['state']!='preparing' or s['ended_at']:raise ProtocolError('session_not_preparing')
            w=self._get(db,'browser_workspaces',s['workspace_id'])
            if w['host_id']!=host_id:raise ProtocolError('stale_host')
            run=self._get(db,'runs',s['run_id'])
            if s['attempt_id']:
                self._assert_not_suppressed(db,s['job_id']);job=self._get(db,'jobs',s['job_id'])
            else:
                job=self._eligible(db,s['job_id'],json.loads(run['settings_json']),s['id'])
            candidate=self._get(db,'candidates',s['identity_id'])
            now=self.now()
            fence=db.execute('SELECT COALESCE(MAX(fence),0)+1 FROM application_attempts WHERE browser_profile=?',(s['workspace_id'],)).fetchone()[0]
            if s['attempt_id']:
                # Explicit paused-session attach: stopped browser; fresh target, same attempt.
                attempt=self._get(db,'application_attempts',s['attempt_id'])
                if self._submission_pending(db,attempt):raise ProtocolError('submission_unknown')
                attempt_id=attempt['id'];fence=attempt['fence']
            else:
                attempt_id=self._create_attempt(db,run,job,candidate,fence,now,'local-session-v1')
                asset_id=json.loads(s['request_key'])[3]
                db.execute('INSERT INTO document_selections VALUES (?,?,?,?,?,?)',(uid(),asset_id,job['id'],attempt_id,'selected',now))
            meta=json.loads(s['metadata_json']);meta['readiness']=readiness
            db.execute("UPDATE application_sessions SET attempt_id=?,target_id=?,state='connected',reason=NULL,connected_at=COALESCE(connected_at,?),driver_seen_at=?,metadata_json=? WHERE id=?",
                       (attempt_id,target_id,now,now,dumps(meta),s['id']))
            db.execute("UPDATE jobs SET status='running',started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",(now,now,job['id']))
            db.execute("UPDATE runs SET state='active',control='running',accepted_at=COALESCE(accepted_at,?),started_at=COALESCE(started_at,?) WHERE id=?",(now,now,run['id']))
            db.execute("UPDATE run_jobs SET state='active' WHERE run_id=? AND job_id=?",(run['id'],job['id']))
            db.execute('INSERT INTO run_sessions(run_id,worker_id,session_id,started_at) VALUES (?,?,?,?)',(run['id'],run['worker_id'],s['driver_id'],now))
            if self._has_question_schema(db):
                db.execute("UPDATE answer_retry_requests SET state='started',session_id=?,started_at=? WHERE job_id=? AND identity_id=? AND state='queued'",
                    (session_id,now,s['job_id'],s['identity_id']))
        # Existing target identity enforcement is reused after the atomic transition.
        self.session_authority=(session_id,s['driver_id'],host_id)
        self.bind_target(attempt_id,worker_id=run['worker_id'],fence=fence,target_id=target_id,url=job['url'])
        return self.session(session_id)

    def session_stopped(self, session_id, *, reason, paused=False, browser_stopped=False):
        if browser_stopped is not True:raise ProtocolError('owned_browser_stop_evidence_required')
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['ended_at']:return dict(s)
            now=self.now();reason=safe_text(reason)
            if s['attempt_id']:
                a=self._get(db,'application_attempts',s['attempt_id'])
                # Process-tree termination establishes quiescence even after a crash.
                db.execute("UPDATE managed_actions SET ended_at=?,status='aborted',uncertainty=1 WHERE attempt_id=? AND ended_at IS NULL",(now,a['id']))
                db.execute("UPDATE application_attempts SET writer_state='idle' WHERE id=?",(a['id'],))
                db.execute("UPDATE owned_targets SET state='closed',evidence=?,updated_at=? WHERE attempt_id=? AND state!='closed'",(reason,now,a['id']))
                pending=self._submission_pending(db,a)
                if pending and not a['completed_at']:paused=False
                if not paused and not a['completed_at']:
                    outcome='submission_unknown' if pending else 'interrupted'
                    self._complete(db,a,outcome,reason,quiescent=True,finish_key=hashlib.sha256(dumps([outcome,reason]).encode()).hexdigest(),reconciled=True)
                if a['completed_at']:paused=False
            state='paused' if paused else 'finished' if s['state']=='finishing' else 'failed' if not s['attempt_id'] else 'stopped'
            db.execute('UPDATE application_sessions SET state=?,reason=?,ended_at=?,target_id=NULL WHERE id=?',(state,reason,None if paused else now,s['id']))
            db.execute('DELETE FROM account_coordination WHERE session_id=?',(s['id'],))
            if s['run_id']:
                db.execute('UPDATE runs SET control=?,state=?,ended_at=? WHERE id=?',('paused' if paused else 'stopped','active' if paused else 'completed',None if paused else now,s['run_id']))
                db.execute('UPDATE run_sessions SET ended_at=? WHERE run_id=? AND ended_at IS NULL',(now,s['run_id']))
            return dict(self._get(db,'application_sessions',s['id']))

    def attach_session(self, session_id, driver_id):
        if not driver_id:raise ProtocolError('driver_required')
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['driver_id']==driver_id and s['state'] in ('connected','waiting','preparing'):return dict(s)
            if s['state']!='paused' or s['ended_at']:raise ProtocolError('stop_previous_driver_before_attach')
            a=self._get(db,'application_attempts',s['attempt_id']) if s['attempt_id'] else None
            if a and self._submission_pending(db,a):raise ProtocolError('submission_unknown')
            db.execute("UPDATE application_sessions SET driver_id=?,state='preparing',reason='Explicit attach after owned browser stopped' WHERE id=?",(driver_id,session_id))
            if a:db.execute('UPDATE application_attempts SET session_id=? WHERE id=?',(driver_id,a['id']))
            db.execute("UPDATE runs SET session_id=?,control='running',state='preparing' WHERE id=?",(driver_id,s['run_id']))
            return dict(self._get(db,'application_sessions',session_id))

    def coordinate_account(self, session_id, *, release=False):
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id);self._local_owner(db,s)
            job=self._get(db,'jobs',s['job_id']);namespace=self._job_account_namespace(db,job)
            candidate=self._get(db,'candidates',s['identity_id'])
            key=(candidate['person_key'],namespace)
            old=db.execute('SELECT * FROM account_coordination WHERE person_key=? AND namespace=?',key).fetchone()
            if old and old['session_id']!=session_id:raise ProtocolError('account_in_use')
            if release:
                db.execute('DELETE FROM account_coordination WHERE person_key=? AND namespace=? AND session_id=?',(*key,session_id))
            elif not old:
                db.execute('INSERT INTO account_coordination VALUES (?,?,?,?)',(*key,session_id,self.now()))
            return {'namespace':namespace,'state':'released' if release else 'owned','session_id':session_id}

    def sessions_view(self):
        with self.tx() as db:
            if not self._has_local_schema(db):return {'sessions':[],'workspaces':[]}
            ids=[r[0] for r in db.execute('SELECT id FROM application_sessions ORDER BY requested_at DESC LIMIT 100')]
            workspaces=[dict(r) for r in db.execute('SELECT id,state,reason,host_seen_at,config_json FROM browser_workspaces')]
        return {'sessions':[self.session_status(sid) for sid in ids],
                'workspaces':[{**w,'config':json.loads(w.pop('config_json'))} for w in workspaces]}
