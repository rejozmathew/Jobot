"""Exercise the shipped grouped inbox, library editor and paginated history."""
from test_dispatch_queue_ui import dashboard_check


FIXTURE = r'''
v.candidates=[{id:'candidate',email:'fixture@example.test'}];
v.jobs=[{id:'job-a',company:'Example',title:'Role A',url:'https://example.test/1',status:'blocked'}];
v.answer_queue={groups:[],inbox:[],ready:[],history_count:2,clusters:[{
 id:'cluster',identity_id:'candidate',email:'fixture@example.test',question:'When can you start?',
 kind:'text',options:[],aliases:['When could you start?'],scope:'global',scope_key:'',request_count:2,
 requests:[{question_id:'q1',revision:0,job_id:'job-a',company:'Example',title:'Role A',url:'https://example.test/1'},
 {question_id:'q2',revision:0,job_id:'job-b',company:'Other',title:'Role B',url:'https://example.test/2'}]}]};
w.draw(v);w.noRefresh();w.drawAnswers(v);
'''


FOCUSED_FIXTURE = FIXTURE + "doc.getElementById('answer-bulk-toggle').click();\n"


def test_learned_answer_shows_distinct_matching_and_form_use_evidence():
    dashboard_check(FIXTURE + r'''
v.answer_library={entries:[{id:'used',identity_id:'candidate',question:'Do you own stock in {company}?',answer:'No',scope:'global',state:'active',revision:2,history:[],
usage:{resolved_questions:4,recorded_form_uses:2,applications:3,last_used_at:'2026-10-06T12:00:00Z',recent:[{kind:'form',job_id:'job-a',company:'Example',title:'Role A',question:'Do you own stock in Example?',library_revision:1,attempt_id:42,at:'2026-10-06T12:00:00Z'}]}}],suggestions:[]};
w.drawAnswers(v);doc.querySelector('nav [data-tab=learned]').click();
const text=doc.getElementById('learned-detail').textContent;
assert(text.includes('4 matched questions')&&text.includes('2 recorded form uses'),'Reuse counts missing');
assert(text.includes('Example')&&text.includes('Attempt 42')&&text.includes('Version 1'),'Evidence lost its application/version');
assert(text.includes('Neither proves submission'),'Matching is misrepresented as submission');
''')


def test_grouped_inbox_saves_application_replies_without_adding_raw_library_entries():
    dashboard_check(FOCUSED_FIXTURE + r'''
const input=doc.getElementById('answer-q1');input.value='After two weeks notice';input.oninput();
let payload;w.fetch=async(path,options)=>{assert(path==='/v1/answer_questions','Save must persist a human application response');payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({questions:[]})};};
const form=doc.querySelector('#answer-groups form');
assert(form.querySelector('[type=submit]').textContent==='Save answer','Primary save still requires adding knowledge');
assert([...form.querySelectorAll('button')].some(b=>b.textContent==='Add reusable answer'),'Optional manual reusable answer is missing');
await form.onsubmit({preventDefault(){}});
assert(payload.answers.length===2,'Matching requests were not answered');
assert(payload.answers[0].answer==='After two weeks notice'&&payload.answers[0].question_id==='q1','Human answer lost');
assert(payload.answers[1].question_id==='q2','Other matching application omitted');
assert(doc.getElementById('answer-receipt').textContent.includes('AI'),'Background learning destination is unclear');
''')


def test_library_editor_preserves_revision_and_conditions():
    dashboard_check(FIXTURE + r'''
doc.getElementById('library-dialog').showModal=function(){this.open=true};doc.getElementById('library-dialog').close=function(){this.open=false};
v.answer_library={entries:[{id:'entry',identity_id:'candidate',question:'Compensation?',answer:'100000',aliases:['Salary?'],
 scope:'company',scope_key:'example',conditions:{country:'us',currency:'USD',period:'year'},state:'active',revision:4,history:[]}],suggestions:[]};
w.drawAnswers(v);doc.querySelector('nav [data-tab=learned]').click();
doc.querySelector('#learned-detail button').onclick();
assert(doc.getElementById('library-question').value==='Compensation?','Editor lost current question');
assert(doc.getElementById('library-company').value==='example'&&!doc.getElementById('library-company-label').hidden,'Company scope hidden');
doc.getElementById('library-answer').value='110000';let payload;
w.fetch=async(path,options)=>{payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({})};};
const form=doc.getElementById('library-form');await form.onsubmit({preventDefault(){},currentTarget:form});
assert(payload.entry_id==='entry'&&payload.expected_revision===4,'Optimistic revision omitted');
assert(payload.answer==='110000'&&payload.conditions.currency==='USD'&&payload.conditions.period==='year','Answer applicability changed');
assert(payload.aliases.join()==='Salary?','Accepted wording lost');
''')


def test_history_is_paginated_and_searchable_without_retry_actions():
    dashboard_check(FIXTURE + r'''
const calls=[];
w.fetch=async(path,options)=>{calls.push(JSON.parse(options.body));return {ok:true,status:200,json:async()=>({groups:[],total:31})};};
doc.querySelector('[data-answer-mode=history]').click();
await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[0].limit===12&&calls[0].offset===0,'History is unbounded');
doc.querySelector('#answer-pagination [data-page=next]').click();await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[1].offset===12,'Next page did not advance');
doc.getElementById('answer-search').value='Example';doc.getElementById('answer-search').oninput();await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[2].search==='example'&&calls[2].offset===0,'Search did not reset pagination');
assert(!doc.querySelector('#answer-groups form'),'History offered application writes');
''')


def test_company_and_role_are_visible_before_answering_and_learned_answers_have_a_top_tab():
    dashboard_check(FOCUSED_FIXTURE + r'''
assert(doc.querySelector('nav [data-tab="learned"]')?.textContent.includes('Learned answers'),'Saved answers have no top-level destination');
const context=doc.querySelector('#answer-groups .answer-context');
assert(context&&!context.closest('details'),'Application context is collapsed');
for(const text of ['Example','Role A','Other','Role B'])assert(context.textContent.includes(text),'Missing application context: '+text);
const row=doc.querySelector('#answer-list button');
assert(row.textContent.includes('Example')&&row.textContent.includes('Role A'),'Question list omits company and role');
assert(doc.getElementById('answer-groups').querySelectorAll('form').length===1,'Inbox stacks editors');
''')


def test_large_inbox_is_paged_and_keeps_selection_and_drafts_during_refresh():
    dashboard_check(FOCUSED_FIXTURE + r'''
const base=v.answer_queue.clusters[0];
v.answer_queue.clusters=Array.from({length:35},(_,i)=>({...base,id:'cluster-'+i,question:'Question '+i,
 requests:[{...base.requests[0],question_id:'q-'+i}],request_count:1}));
w.drawAnswers(v);
assert(doc.querySelectorAll('#answer-list .answer-list-item').length===12,'Inbox renders an unbounded list');
assert(doc.querySelectorAll('#answer-groups form').length===1,'Multiple answer forms pile up');
let input=doc.getElementById('answer-q-0');input.value='Draft retained';input.oninput();
doc.querySelectorAll('#answer-list button')[1].click();
assert(doc.getElementById('answer-q-1'),'Selecting a question did not change the focused editor');
v.answer_queue.clusters=[...v.answer_queue.clusters].reverse();w.drawAnswers(v);
assert(doc.getElementById('answer-q-1'),'Polling changed the selected question');
const first=[...doc.querySelectorAll('#answer-list button')].find(b=>b.dataset.answerId==='cluster-0');first.click();
assert(doc.getElementById('answer-q-0').value==='Draft retained','Changing question lost a draft');
doc.querySelector('#answer-pagination [data-page="previous"]').click();
assert(doc.querySelectorAll('#answer-list .answer-list-item').length===12,'Next page is unbounded');
assert(doc.querySelector('#answer-pagination').textContent.includes('13–24 of 35'),'Page position is unclear');
''')


def test_save_has_a_visible_destination_advances_the_inbox_and_keeps_other_drafts():
    dashboard_check(FOCUSED_FIXTURE + r'''
const next={...v.answer_queue.clusters[0],id:'next',question:'Another question',requests:[{...v.answer_queue.clusters[0].requests[0],question_id:'q3'}]};
v.answer_queue.clusters.push(next);w.drawAnswers(v);
doc.querySelector('[data-answer-id=next]').click();let input=doc.getElementById('answer-q3');input.value='My next draft';input.oninput();
doc.querySelector('[data-answer-id=cluster]').click();input=doc.getElementById('answer-q1');input.value='Two weeks';input.oninput();
w.fetch=async()=>({ok:true,status:200,json:async()=>({id:'saved'})});
await doc.querySelector('#answer-groups form').onsubmit({preventDefault(){}});
assert(!doc.getElementById('answer-receipt').hidden&&doc.getElementById('answer-receipt').textContent.includes('AI'),'Save destination is unclear');
v.answer_queue.clusters=[next];v.answer_library={entries:[{id:'saved',identity_id:'candidate',question:'When can you start?',answer:'Two weeks',scope:'global',state:'active',revision:1,history:[]}],suggestions:[{id:'source',identity_id:'candidate',question:'When can you start?',state:'pending',source:{question:'When can you start?',answer:'Two weeks',job_id:'job-a',company:'Example',title:'Role A'}}]};
w.drawAnswers(v);
assert(doc.getElementById('answer-q3').value==='My next draft','Saving failed to advance or lost another draft');
doc.querySelector('#answer-receipt button').click();
assert(!doc.getElementById('tab-learned').hidden&&doc.getElementById('tab-answers').hidden,'View saved answer did not open its destination');
assert(doc.getElementById('learned-detail').textContent.includes('Two weeks'),'Original response cannot be found in AI learning activity');
''')


def test_learned_answers_use_human_role_labels_and_bound_the_list():
    dashboard_check(FIXTURE + r'''
v.answer_library={entries:Array.from({length:35},(_,i)=>({id:'entry-'+i,identity_id:'candidate',question:'Learned question '+i,answer:'Current answer '+i,
 scope:'job',scope_key:'job-a',state:'active',revision:1,history:[]})),suggestions:[]};w.drawAnswers(v);
doc.querySelector('nav [data-tab=learned]').click();
assert(doc.querySelectorAll('#learned-list .answer-list-item').length===12,'Learned answers are an unbounded stack');
assert(doc.querySelectorAll('#learned-detail .answer-application').length===1,'Multiple learned-answer editors are stacked');
assert(doc.getElementById('learned-detail').textContent.includes('Example')&&doc.getElementById('learned-detail').textContent.includes('Role A'),'Learned answer shows an opaque job ID');
doc.querySelector('#learned-pagination [data-page=next]').click();
assert(doc.querySelector('#learned-pagination').textContent.includes('13–24 of 35'),'Learned-answer pagination did not advance');
''')


def test_editing_a_learned_answer_for_a_job_outside_the_visible_queue_keeps_its_scope():
    dashboard_check(FIXTURE + r'''
doc.getElementById('library-dialog').showModal=function(){this.open=true};
v.answer_library={entries:[{id:'entry',identity_id:'candidate',question:'Why this role?',answer:'Original answer',scope:'job',scope_key:'archived-job',state:'active',revision:1,history:[],
 application:{id:'archived-job',company:'Earlier Employer',title:'Earlier Position',url:'https://example.test/earlier'}}],suggestions:[]};w.drawAnswers(v);
doc.querySelector('nav [data-tab=learned]').click();
assert(doc.getElementById('learned-detail').textContent.includes('Earlier Employer')&&doc.getElementById('learned-detail').textContent.includes('Earlier Position'),'Saved job context disappeared outside the queue');
doc.querySelector('#learned-detail button').click();
assert(doc.getElementById('library-job').value==='archived-job','Opening the editor silently changed the application scope');
''')
