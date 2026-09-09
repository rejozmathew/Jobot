"""Private verification uses synthetic DOM and fake mailbox results exclusively."""
import asyncio
from datetime import datetime, timezone
import json
import subprocess

import pytest

from job_applier import browser_controls, hermes_gmail, managed_credentials
from job_applier.application_answers import save_answer_history
from test_greenhouse_recovery import form_dom
from test_workday_dom import JSDOM


SEGMENTS='<fieldset><legend>We emailed you an eight-character security code.</legend>'+''.join(
    f'<input id="code-{i}" maxlength="1" aria-label="{ "Security code" if i==0 else "" }">' for i in range(8))+'</fieldset>'


def test_every_verification_segment_is_private_and_excluded_from_answer_history():
    result=form_dom(SEGMENTS,[{'method':'verification'},{'method':'fill','selector':'#code-7','value':'X'},
                              {'method':'answers','page':'application_questions'}])
    group=result['results'][0]['groups'][0]
    assert group['kind']=='email_code' and group['length']==8 and len(group['refs'])==8
    assert result['results'][1]['committed'] is True
    assert all(f['private'] for f in result['observation']['inventory'])
    assert result['results'][2]['answers']==[]


def test_security_code_is_filtered_from_python_history_too(tmp_path):
    package={'job':{'id':'fixture','url':'https://boards.greenhouse.io/example/jobs/12345'},'attempt':{}}
    result=save_answer_history({'spool_dir':str(tmp_path)},package,1,[
        {'field':'security_code','question':'Security code','answer':'ABCD2345'}],page='form',source='fixture')
    assert result=={} and not (tmp_path/'answers/attempt-1.json').exists()


def verification_dom(*,bad_ref=False,short_value=False):
    if not JSDOM.exists():pytest.skip('optional jsdom fixture dependency not installed')
    script=r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(d.html,{url:'https://boards.greenhouse.io/example/jobs/12345',runScripts:'outside-only'}).window;
w.HTMLElement.prototype.getClientRects=()=>[{width:100,height:20}];
w.HTMLElement.prototype.getBoundingClientRect=()=>({width:100,height:20});
const form=w.eval(d.form),group=form({method:'verification'}).groups[0];
const refs=[...group.refs];if(d.bad_ref)refs[7]='form:stale';
w.eval('('+d.fill+')')({refs,challenge_ref:group.challenge_ref,value:d.value}).then(result=>{
 console.log(JSON.stringify({result,values:[...w.document.querySelectorAll('input')].map(e=>e.value)}));w.close();});
'''
    result=subprocess.run(['node','-e',script,str(JSDOM)],input=json.dumps({
        'html':SEGMENTS,'form':browser_controls.FORM,'fill':managed_credentials.FILL_VERIFICATION,
        'bad_ref':bad_ref,'value':'ABCD234' if short_value else 'ABCD2345'}),
        text=True,capture_output=True,check=True,timeout=10)
    return json.loads(result.stdout)


@pytest.mark.parametrize('bad_ref,short_value',[(True,False),(False,True)])
def test_all_refs_and_length_are_validated_before_any_segment_mutation(bad_ref,short_value):
    result=verification_dom(bad_ref=bad_ref,short_value=short_value)
    assert result['result']['values_committed'] is False and result['values']==['']*8
    assert 'ABCD234' not in json.dumps(result['result'])


def test_eight_segments_fill_together_and_return_only_commitment():
    result=verification_dom()
    assert result['result']['values_committed'] and result['values']==list('ABCD2345')
    assert 'ABCD2345' not in json.dumps(result['result'])


def test_verification_errors_do_not_include_mail_or_code(monkeypatch):
    async def fail(*args,**kwargs):raise RuntimeError('ABCD2345 body and token should never escape')
    monkeypatch.setattr(managed_credentials,'fill_page_verification',fail)
    result=asyncio.run(managed_credentials.fill_page_credentials({}, {}, None, {'mode':'verification'}))
    assert result['values_committed'] is False and 'ABCD2345' not in json.dumps(result)


def test_code_like_strings_are_redacted_from_all_progress_text():
    from job_applier.managed_redaction import safe_payload
    result=safe_payload({'activity':'Security code: ABCD2345','evidence':'verification_code=ABCD2345'})
    assert 'ABCD2345' not in json.dumps(result)


@pytest.mark.parametrize('label',['Security code','Authentication code','verification_code'])
def test_verification_code_cannot_enter_human_answer_queue(label):
    from job_applier.managed_questions import question_data
    from job_applier.managed_shared import ProtocolError
    with pytest.raises(ProtocolError,match='private_question_prohibited'):
        question_data(field='challenge',question=label,kind='text')


def test_mailbox_handoff_exposes_only_the_existing_configured_invocation(tmp_path):
    script=tmp_path/'fixture_script.py';token=tmp_path/'fixture_token.json'
    script.write_text('# synthetic script');token.write_text('synthetic-secret-not-to-be-read')
    result=hermes_gmail.mailbox_handoff({'gmail_script':str(script),'mailbox_token_path':str(token)})
    assert result['available'] and result['wrapper_argv'][-1]=='gmail'
    assert '--script' in result['wrapper_argv'] and 'synthetic-secret' not in json.dumps(result)
    assert hermes_gmail.mailbox_handoff({})['available'] is False


@pytest.mark.parametrize('mode',['top','cross'])
def test_real_segmented_group_resend_fresh_fill_and_stale_refs_are_private(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    from job_applier.browser_frames import resolve_control
    html=SEGMENTS.replace('</fieldset>','<button type="button" id="resend">Resend code</button></fieldset>')+'''
<script>resend.onclick=e=>{if(e.isTrusted)document.body.dataset.resent='true'};</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,submissions):
            screen=await browser_controls.observe(page,package);group=screen['verification']['groups'][0]
            base={'mode':'verification','challenge_ref':group['challenge_ref'],'refs':group['refs']}
            resent=await managed_credentials.fill_page_verification({},package,page,dict(base,action='resend',resend_ref=group['resend_ref']))
            assert resent.get('resend_requested') and resent.get('requested_at'),resent
            group=resent['group'];base.update(refs=group['refs'],challenge_ref=group['challenge_ref'])
            document,_=await resolve_control(page,{'ref':group['refs'][0]})
            assert await document.evaluate("document.body.dataset.resent==='true'")
            wrong=await managed_credentials.fill_page_verification({},package,page,dict(base,refs=group['refs'][:-1],action='fill'))
            assert wrong['error']=='verification_group_changed'
            assert await document.evaluate("[...document.querySelectorAll('input')].every(e=>!e.value)")
            filled=await managed_credentials.fill_page_verification({},package,page,dict(base,action='fill',value='ABCD2345'))
            assert filled['values_committed']
            mask=await document.evaluate(managed_credentials.MASK_CREDENTIALS)
            assert mask['masked_count']==8
            assert await document.evaluate("[...document.querySelectorAll('input')].every(e=>e.style.visibility==='hidden')")
            await document.evaluate(managed_credentials.UNMASK_CREDENTIALS)
            answers=await document.evaluate_function(browser_controls.FORM,{'method':'answers','page':'application_questions'})
            assert answers['answers']==[] and 'ABCD2345' not in json.dumps([resent,wrong,filled,answers])
            assert submissions==[]
    asyncio.run(run())
