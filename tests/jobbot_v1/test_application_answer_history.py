"""Small checks for the private answer journal and unchanged-value selection."""
import asyncio
import json
from pathlib import Path

from job_applier.application_answers import save_answer_history,capture_answers
from job_applier.browser_controls import form_action


def test_answer_history_keeps_portal_context_and_answer_changes(tmp_path):
    config={'spool_dir':str(tmp_path)}
    package={'job':{'id':'job-1','url':'https://tenant.example/jobs/1','company':'Example','title':'Director'},
             'attempt':{'local_session_id':'session-1'},'platform':'workday','namespace':'tenant.example/Jobs'}
    answers=[{'field':'salary','question':'Expected annual compensation?','answer':'250000'}]
    first=save_answer_history(config,package,1,answers,page='application_questions',source='employer_form')
    assert first['answers_added']==1
    assert save_answer_history(config,package,1,answers,page='application_questions',source='employer_form')['answers_added']==0
    answers[0]['answer']='280000'
    save_answer_history(config,package,1,answers,page='application_questions',source='executor_select',basis='approved profile policy')
    saved=json.loads(Path(first['answer_history_path']).read_text())
    assert saved['company']=='Example' and saved['portal_namespace']=='tenant.example/Jobs'
    assert saved['session_id']=='session-1' and saved['job_id']=='job-1'
    assert [row['answer'] for row in saved['answers']]==['250000','280000']
    assert saved['answers'][0]['answer_basis']=='not_recorded'
    assert saved['answers'][1]['answer_basis']=='approved profile policy'


def test_answer_history_excludes_secret_controls_and_secret_payloads(tmp_path):
    package={'job':{'url':'https://tenant.example/jobs/1'}}
    answers=[{'field':'password','question':'Password?','answer':'private-value'},
             {'field':'question','question':'Describe your qualifications?','answer':'password=private-value'}]
    assert save_answer_history({'spool_dir':str(tmp_path)},package,1,answers,page='form',source='employer_form')=={}
    assert not list(tmp_path.rglob('*.json'))


def test_selected_closed_dropdown_does_not_open_again():
    class Page:
        async def evaluate_function(self,script,args):
            assert args['method']=='inspect'
            return {'tag':'BUTTON','haspopup':'listbox','expanded':'false','value':'LinkedIn','label':'LinkedIn'}
    result=asyncio.run(form_action(Page(),{'method':'select','ref':'observed','label':'LinkedIn'}))
    assert result['committed'] and result['unchanged']


def test_observed_company_completes_url_only_intake_metadata(tmp_path):
    class Page:
        async def evaluate_function(self,script,args):
            return {'answers':[{'field':'eligible','question':'Are you eligible?','answer':'Yes'}],
                    'context':{'company':'Example','job_title':'Director','source':'simplify_job_card'}}
    result=asyncio.run(capture_answers(Page(),{'spool_dir':str(tmp_path)},
        {'job':{'url':'https://tenant.example/jobs/1'}},{'attempt_id':2}))
    history=json.loads(Path(result['answer_history_path']).read_text())
    assert history['company']=='Example' and history['job_title']=='Director'
    assert history['company_source']=='simplify_job_card' and history['portal_namespace']=='tenant.example'
