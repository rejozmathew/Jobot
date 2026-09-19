"""External Apply target correlation and owned-session handoff regressions."""
import asyncio
import hashlib
import json
import os
import sys

import pytest

from job_applier.cdp_client import arm_target_observation, wait_for_apply_target
from job_applier.application_runtime import external_apply_destination, click_and_follow_external_apply
from job_applier.managed import Service
from job_applier.managed_shared import ProtocolError
from job_applier.workspace_process import process_identity


LINKEDIN="https://www.linkedin.com/jobs/view/424242"
EXTERNAL="https://myjobs.adp.com/acme/cx/job-details?reqId=424242"


def target(target_id,url,*,opener=None,context="ctx"):
    value={"targetId":target_id,"type":"page","url":url,"browserContextId":context}
    if opener is not None:value["openerId"]=opener
    return value


def observe(sequences,expected=EXTERNAL):
    before=sequences[0]
    observation=arm_target_observation("http://127.0.0.1:9222","linkedin",expected,targets=before)
    state={"index":0}
    async def current_url():
        rows=sequences[min(state["index"],len(sequences)-1)]
        return next(row["url"] for row in rows if row["targetId"]=="linkedin")
    async def inventory():
        rows=sequences[min(state["index"],len(sequences)-1)]
        state["index"]+=1
        return rows
    return asyncio.run(wait_for_apply_target(observation,inventory=inventory,current_url=current_url,timeout=.1,poll_interval=.001))


def test_easy_apply_in_page_does_not_arm_popup_observation():
    assert arm_target_observation("http://127.0.0.1:9222","linkedin",None,
        targets=[target("linkedin",LINKEDIN)]) is None
    assert external_apply_destination({"text":"Easy Apply","href":""},LINKEDIN) is None


def test_external_apply_accepts_same_host_and_unwraps_linkedin_redirect():
    same_host="https://careers.example.com/jobs/42/apply?req=42"
    assert external_apply_destination(
        {"text":"Apply now","href":same_host},
        "https://careers.example.com/jobs/42",
    ) == same_host
    wrapped=("https://www.linkedin.com/redir/redirect?url="
             "https%3A%2F%2Fcareers.example.com%2Fjobs%2F42%2Fapply%3Freq%3D42")
    assert external_apply_destination({"text":"Apply","href":wrapped},LINKEDIN) == same_host
    safety=("https://www.linkedin.com/safety/go/?url="
            "https%3A%2F%2Fcareers.example.com%2Fjobs%2F42%2Fapply%3Freq%3D42&urlhash=x")
    assert external_apply_destination({"text":"Apply","href":safety},LINKEDIN) == same_host


@pytest.mark.parametrize("href",[
    "http://127.0.0.1:8080/apply",
    "http://localhost/apply",
    "http://169.254.169.254/latest/meta-data",
    "https://user:secret@careers.example.com/apply",
])
def test_external_apply_rejects_nonpublic_or_credentialed_destinations(href):
    assert external_apply_destination({"text":"Apply","href":href},LINKEDIN) is None


def test_external_apply_observation_is_armed_before_click(monkeypatch):
    order=[]
    class Page:
        async def evaluate(self,script):return LINKEDIN
    class Browser:base_url="http://127.0.0.1:9222"
    class Client:
        def call(self,operation,**values):
            order.append((operation,values));return {"target_id":"adp"}
    def arm(*args,**kwargs):order.append("arm");return object()
    async def wait(*args,**kwargs):order.append("wait");return {"target_id":"adp","url":EXTERNAL,"kind":"popup"}
    monkeypatch.setattr("job_applier.cdp_client.arm_target_observation",arm)
    monkeypatch.setattr("job_applier.cdp_client.wait_for_apply_target",wait)
    async def activate():order.append("click");return {"clicked":True,"execution":"clicked"}
    result=asyncio.run(click_and_follow_external_apply(Browser(),Page(),
        {"text":"Apply","href":EXTERNAL},activate,Client(),{"attempt_id":1,"worker_id":"w","fence":1},"linkedin"))
    assert order[0:3]==["arm","click","wait"]
    assert order[3][0]=="handoff_target" and result["target_handoff"]["target_id"]=="adp"


def test_external_apply_same_tab_is_selected():
    result=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",EXTERNAL)],
    ])
    assert result=={"target_id":"linkedin","url":EXTERNAL,"kind":"same_tab"}


def test_external_apply_popup_is_correlated_by_opener_context_and_destination():
    result=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",LINKEDIN),target("adp",EXTERNAL,opener="linkedin")],
    ])
    assert result=={"target_id":"adp","url":EXTERNAL,"kind":"popup"}


def test_unrelated_or_ambiguous_popup_is_not_adopted():
    unrelated=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",LINKEDIN),target("mail","https://mail.example.test",opener="other")],
    ])
    assert unrelated is None
    wrong_requisition=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",LINKEDIN),target("other-adp","https://myjobs.adp.com/acme/cx/job-details?reqId=999",opener="linkedin")],
    ])
    assert wrong_requisition is None
    ambiguous=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",LINKEDIN),target("a",EXTERNAL,opener="linkedin"),target("b",EXTERNAL,opener="linkedin")],
    ])
    assert ambiguous is None


def test_about_blank_popup_is_waited_through_before_handoff():
    result=observe([
        [target("linkedin",LINKEDIN)],
        [target("linkedin",LINKEDIN),target("adp","about:blank",opener="linkedin")],
        [target("linkedin",LINKEDIN),target("adp",EXTERNAL,opener="linkedin")],
    ])
    assert result["target_id"]=="adp" and result["url"]==EXTERNAL


def connected(tmp_path):
    service=Service.create(tmp_path/"managed.db",instance_id="handoff-fixture")
    service.identity(identity_id="candidate",person_key="person",email="candidate@example.test",profile={})
    resume=tmp_path/"resume.pdf";resume.write_bytes(b"fixture")
    asset=service.register_asset(identity_id="candidate",kind="resume",version="1",storage_ref=resume.as_uri(),
        sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),provenance={"source":"synthetic"})
    job=service.intake(url=LINKEDIN,source_type="linkedin_bridge",source_id="li:424242")
    service.eligibility(job["id"],"ready",reason="synthetic")
    workspace={"id":"workspace","user_data_dir":str(tmp_path/"profile"),"browser_executable":sys.executable,
        "cdp_url":"http://127.0.0.1:19777","mode":"headed"}
    service.configure_workspaces([workspace])
    session=service.reserve_session(request_id="request",job_id=job["id"],identity_id="candidate",driver_id="driver",
        workspace_ids=["workspace"],concurrency_limit=1,resume_asset_id=asset["id"])
    service.host_registered("workspace","host",process_identity(os.getpid()))
    session=service.session_connected(session["id"],"host","linkedin",{"synthetic":True})
    attempt=service.attempt(session["attempt_id"])
    service.session_authority=(session["id"],"driver","host")
    owner={"attempt_id":attempt["id"],"worker_id":attempt["worker_id"],"fence":attempt["fence"]}
    return service,session,owner,workspace


def test_target_handoff_atomically_updates_owned_session_and_next_browser_action(tmp_path,monkeypatch):
    service,session,owner,workspace=connected(tmp_path)
    changed=service.handoff_target(**owner,current_target_id="linkedin",new_target_id="adp",url=EXTERNAL,expected_url=EXTERNAL,
        evidence="Observed external Apply popup with matching opener and destination")
    assert changed["session_id"]==session["id"] and changed["target_id"]=="adp"
    assert service.session(session["id"])["target_id"]=="adp"
    with service.tx() as db:
        assert db.execute("SELECT state FROM owned_targets WHERE attempt_id=? AND target_id='linkedin'",(owner["attempt_id"],)).fetchone()[0]=="preserved"
        assert db.execute("SELECT state FROM owned_targets WHERE attempt_id=? AND target_id='adp'",(owner["attempt_id"],)).fetchone()[0]=="open"

    from job_applier.workspace_host import WorkspaceHost
    seen={}
    def fake_action(config,client,ownership,package,target_id,params):
        seen.update(target_id=target_id,method=params["method"]);return {"target_id":target_id}
    monkeypatch.setattr("job_applier.application_runtime.browser_action",fake_action)
    host=object.__new__(WorkspaceHost);host.service=service
    host.config={"db_path":str(service.db_path),"instance_id":service.instance_id};host.workspace_id="workspace";host.host_id="host"
    host.workspace=workspace
    result=host._dispatch({"instance_id":service.instance_id,"session_id":session["id"],"driver_id":"driver",
        "operation":"browser","parameters":{"method":"screenshot"}})
    assert result["target_id"]=="adp" and seen=={"target_id":"adp","method":"screenshot"}


def test_target_handoff_rejects_foreign_owner_endpoint_and_unverified_destination(tmp_path):
    service,session,owner,_=connected(tmp_path)
    with pytest.raises(ProtocolError,match="stale_owner"):
        service.handoff_target(**dict(owner,worker_id="foreign"),current_target_id="linkedin",new_target_id="adp",url=EXTERNAL,evidence="x")
    with pytest.raises(ProtocolError,match="target_not_owned"):
        service.handoff_target(**owner,current_target_id="foreign",new_target_id="adp",url=EXTERNAL,evidence="x")
    with pytest.raises(ProtocolError,match="target_job_mismatch"):
        service.handoff_target(**owner,current_target_id="linkedin",new_target_id="evil",url="https://evil.example.test/apply",evidence="x")
