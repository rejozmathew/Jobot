"""Exercise shipped Workday DOM observer in jsdom (synthetic, no portals)."""
import json
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
JSDOM=ROOT/'artifacts/jobbot-v1-private/dom-test/node_modules/jsdom'
SCRIPT=ROOT/'job_applier/browser_helpers/workday_observe.js'


def observe(html, **args):
    assert SCRIPT.exists(), 'Workday observer must exist'
    if not JSDOM.exists():
        pytest.skip('optional jsdom fixture dependency not installed')
    harness=r'''
const fs=require('fs'); const {JSDOM}=require(process.argv[1]); const d=JSON.parse(fs.readFileSync(0,'utf8'));
const dom=new JSDOM(d.html,{url:'https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1/applyManually',runScripts:'outside-only'});
dom.window.HTMLElement.prototype.getBoundingClientRect=function(){return this.hidden?{width:0,height:0}:{width:100,height:20}};
const result=dom.window.eval(d.script)(d.args); console.log(JSON.stringify(result));
'''
    result=subprocess.run(['node','-e',harness,str(JSDOM)],input=json.dumps({'html':html,'script':SCRIPT.read_text(),'args':args}),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def test_current_step_not_site_heading_and_upload_toast_not_error():
    s=observe('<h1>Careers</h1><h2>My Experience</h2><div role="alert">resume.pdf successfully uploaded</div><button>Save and Continue</button>',resume_name='resume.pdf',requisition='R1')
    assert s['step']=='my_experience'
    assert s['blocking_errors']==[]
    assert s['resume_attached'] is True
    assert s['native']['continue']['enabled'] is True


def test_simplify_success_does_not_prove_employer_submission():
    s=observe('<h1>Candidate Home</h1><div class="simplify-jobs-shadow-root"><h2>Application Submitted!</h2>Role R1</div><p>Thank you for your interest</p>',requisition='R1')
    assert s['submitted'] is False


def test_submission_must_match_specific_employer_row():
    s=observe('<h1>Candidate Home</h1><table><tr><td>Role R1</td><td>Application Submitted</td></tr></table>',requisition='R1')
    assert s['submitted'] is True
    assert observe('<table><tr><td>Role R2</td><td>Application Submitted</td></tr><tr><td>Role R1</td><td>Draft</td></tr></table>',requisition='R1')['submitted'] is False


def test_auth_fields_return_only_selectors_never_credentials():
    s=observe('<h2>Create Account</h2><input id="email" type="email" value="private@example.test"><input id="pw" type="password" value="never-log-me"><input id="confirm" type="password">')
    assert s['auth'] is True
    assert s['auth_refs']['email_ref']=='[id="email"]'
    assert 'never-log-me' not in json.dumps(s)
    assert 'private@example.test' not in json.dumps(s)
