"""Bulk replies and learning receipts use synthetic ledger and UI evidence."""
from test_answer_queue import connected, request
from test_answer_learning import reply, synthesis
from test_answer_library_ui import FIXTURE
from test_dispatch_queue_ui import dashboard_check


def test_answered_live_session_is_history_until_browser_stops(tmp_path):
    service, session, owner, _, _ = connected(tmp_path)
    q = request(service, owner)
    service.answer_questions(answers=[dict(question_id=q['id'], answer='Yes', expected_revision=0)])
    assert service.answer_queue()['ready'] == []
    assert service.answer_queue_history()['groups'][0]['browser_stopped'] is False
    service.finish(**owner, outcome='blocked', evidence='Synthetic stopped session', quiescent=True)
    service.session_stopped(session['id'], reason='Fixture stopped', browser_stopped=True)
    assert len(service.answer_queue()['ready']) == 1


def test_learning_activity_includes_completed_extraction_and_exact_source(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    q = reply(service, owner)
    result = service.learn_answers(generator=synthesis)
    view = service.answer_library()
    assert view['learning']['learned'] == 1
    assert view['learning']['total'] == 1
    activity = view['suggestions'][0]
    assert activity['entry_id'] == result['entry_id']
    assert activity['source_id'] == q['id']
    assert activity['updated_at'] and activity['attempts'] == 1


def test_impact_deduplicates_applications_across_answers(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    for index in range(2):
        entry = service.save_library_answer(identity_id='candidate', question=f'Question {index}?', answer='No')
        request(service, owner, field=f'field{index}', question=entry['question'])
    impact = service.answer_library()['impact']
    assert impact['applications'] == 1 and impact['resolved_questions'] == 2
    assert impact['recorded_form_uses'] == 0 and len(impact['recent_applications']) == 1


def test_bulk_answers_preserve_drafts_and_save_one_revision_checked_batch():
    dashboard_check(FIXTURE + r'''
const base=v.answer_queue.clusters[0];
v.answer_queue.clusters.push({...base,id:'second',question:'Another question?',requests:[{...base.requests[0],question_id:'q3'}]});
w.drawAnswers(v);doc.getElementById('answer-bulk-toggle').click();
let one=doc.getElementById('answer-q1'),two=doc.getElementById('answer-q3');
one.value='Two weeks';one.oninput();two.value='Yes';two.oninput();
doc.getElementById('answer-search').value='Another';doc.getElementById('answer-search').oninput();
assert(doc.getElementById('answer-save-drafts').textContent.includes('2'),'Hidden draft lost from save count');
const calls=[];w.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,status:200,json:async()=>({questions:[]})};};
await doc.getElementById('answer-save-drafts').onclick();
assert(calls.length===1&&calls[0].path==='/v1/answer_questions','Batch made per-question writes');
assert(calls[0].body.answers.length===3,'One draft did not cover both matching applications');
assert(calls[0].body.answers.every(a=>a.expected_revision===0),'Revision checks omitted');
assert(doc.getElementById('answer-receipt').textContent.includes('2 questions'),'Receipt omits count');
''')


def test_bulk_failed_save_keeps_all_drafts_and_does_not_queue():
    dashboard_check(FIXTURE + r'''
doc.getElementById('answer-bulk-toggle').click();const input=doc.getElementById('answer-q1');input.value='Two weeks';input.oninput();
w.fetch=async()=>({ok:false,status:409,json:async()=>({error:'answer_revision_conflict'})});
await doc.getElementById('answer-save-drafts').onclick();
assert(doc.getElementById('answer-q1').value==='Two weeks','Conflict discarded draft');
assert(!doc.getElementById('answer-save-drafts').disabled,'Draft cannot be retried');
''')


def test_bulk_partial_save_retries_only_the_unsaved_chunk():
    dashboard_check(FIXTURE + r'''
const cluster=v.answer_queue.clusters[0],base=cluster.requests[0];
cluster.requests=Array.from({length:101},(_,i)=>({...base,question_id:'large-'+i,job_id:'job-'+i}));
w.drawAnswers(v);doc.getElementById('answer-bulk-toggle').click();
const input=doc.getElementById('answer-large-0');input.value='Two weeks';input.oninput();
const calls=[];w.fetch=async(path,options)=>{calls.push(JSON.parse(options.body));return {ok:calls.length!==2,status:calls.length===2?409:200,json:async()=>calls.length===2?{error:'answer_revision_conflict'}:{}};};
await doc.getElementById('answer-save-drafts').onclick();
assert(calls.length===2&&calls[0].answers.length===100&&calls[1].answers.length===1,'Unexpected batch sizes');
assert(doc.getElementById('answer-receipt').textContent.includes('100 applications'),'Partial success receipt is wrong');
await doc.getElementById('answer-save-drafts').onclick();
assert(calls[2].answers.length===1&&calls[2].answers[0].question_id==='large-100','Already saved replies were repeated');
assert(doc.getElementById('answer-save-drafts').disabled,'Saved draft did not clear');
''')


def test_bulk_single_position_save_clears_the_scoped_draft():
    dashboard_check(FIXTURE + r'''
doc.getElementById('answer-bulk-toggle').click();
const scope=doc.querySelector('select[aria-label="Applications for When can you start?"]');scope.value='job-b';scope.onchange();
const input=doc.getElementById('answer-q1');input.value='Two weeks';input.oninput();let payload;
w.fetch=async(path,options)=>{payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({})};};
await doc.getElementById('answer-save-drafts').onclick();
assert(payload.answers.length===1&&payload.answers[0].question_id==='q2','Scope expanded to other applications');
assert(doc.getElementById('answer-save-drafts').disabled,'Unselected requests kept a phantom draft');
''')


def test_focused_save_keeps_revision_from_when_the_draft_was_started():
    dashboard_check(FIXTURE + r'''
let input=doc.getElementById('answer-q1');input.value='Two weeks';input.oninput();
v.answer_queue.clusters[0].requests[0].revision=2;w.drawAnswers(v);let payload;
w.fetch=async(path,options)=>{payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({})};};
await doc.querySelector('#answer-groups form').onsubmit({preventDefault(){}});
assert(payload.answers[0].expected_revision===0,'Polling silently rebased a stale draft');
''')


def test_bulk_draft_survives_matching_application_reordering():
    dashboard_check(FIXTURE + r'''
doc.getElementById('answer-bulk-toggle').click();const input=doc.getElementById('answer-q1');input.value='Two weeks';input.oninput();
v.answer_queue.clusters[0].requests.reverse();w.drawAnswers(v);
assert(doc.getElementById('answer-q2').value==='Two weeks','Reordering matching applications hid the draft');
''')


def test_successful_learning_activity_links_to_result_and_shows_total():
    dashboard_check(FIXTURE + r'''
v.answer_library={entries:[{id:'result',identity_id:'candidate',question:'General question?',answer:'General answer',scope:'global',state:'active',origin:'ai',revision:1}],
 suggestions:[{id:'source',identity_id:'candidate',state:'learned',question:'General question?',entry_id:'result',source:{question:'Original?',answer:'Original reply'},attempts:1}],learning:{total:150,learned:130},impact:{applications:4,resolved_questions:7,recorded_form_uses:2}};
w.drawAnswers(v);doc.querySelector('[data-learned-mode=suggestions]').click();
assert(doc.getElementById('learned-summary').textContent.includes('150'),'Truncated activity is presented as complete');
assert(doc.getElementById('learning-impact').textContent.includes('4'),'Application impact not visible');
const link=[...doc.querySelectorAll('#learned-detail button')].find(b=>b.textContent==='View learned answer');assert(link,'No link from completed extraction to result');link.click();
assert(doc.getElementById('learned-detail').textContent.includes('General answer'),'Wrong result opened');
''')


def test_conflict_review_labels_current_and_proposed_values():
    dashboard_check(FIXTURE + r'''
doc.getElementById('library-dialog').showModal=function(){this.open=true};
v.answer_library={entries:[{id:'current',identity_id:'candidate',question:'Salary?',answer:'100000',scope:'global',state:'active',revision:3}],suggestions:[{id:'conflict',identity_id:'candidate',question:'Salary?',answer:'110000',scope:'global',state:'conflict',existing_entry_id:'current',source:{question:'Salary?',answer:'110000'}}]};
w.drawAnswers(v);doc.querySelector('[data-learned-mode=suggestions]').click();
[...doc.querySelectorAll('#learned-detail button')].find(b=>b.textContent==='Review proposed knowledge').click();
assert(doc.getElementById('library-comparison').textContent.includes('100000'),'Current answer absent');
assert(doc.getElementById('library-answer-label').textContent==='Proposed answer','Proposed answer mislabeled as current');
''')
