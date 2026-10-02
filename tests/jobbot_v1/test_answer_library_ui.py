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


def test_grouped_inbox_saves_one_reusable_answer_with_aliases():
    dashboard_check(FIXTURE + r'''
assert(doc.getElementById('answer-count').textContent==='(1)','Badge counts requests rather than distinct questions');
assert(doc.querySelectorAll('#answer-groups .answer-application').length===1,'Duplicate requests still create separate cards');
const input=doc.getElementById('answer-q1');input.value='After two weeks notice';input.oninput();
let payload;w.fetch=async(path,options)=>{assert(path==='/v1/save_library_answer','Saving launched an application or wrote a browser');payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({id:'saved'})};};
const form=doc.querySelector('#answer-groups form');await form.onsubmit({preventDefault(){}});
assert(payload.answer==='After two weeks notice'&&payload.scope==='global','Reusable answer lost meaning or scope');
assert(payload.aliases[0]==='When could you start?'&&payload.identity_id==='candidate','Alias or candidate omitted');
assert(!JSON.stringify(payload).includes('ref'),'Browser refs leaked into reusable knowledge');
''')


def test_library_editor_preserves_revision_and_conditions():
    dashboard_check(FIXTURE + r'''
doc.getElementById('library-dialog').showModal=function(){this.open=true};doc.getElementById('library-dialog').close=function(){this.open=false};
v.answer_library={entries:[{id:'entry',identity_id:'candidate',question:'Compensation?',answer:'100000',aliases:['Salary?'],
 scope:'company',scope_key:'example',conditions:{country:'us',currency:'USD',period:'year'},state:'active',revision:4,history:[]}],suggestions:[]};
doc.getElementById('answer-view').value='library';doc.getElementById('answer-view').onchange();
doc.querySelector('#answer-groups button').onclick();
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
doc.getElementById('answer-view').value='history';doc.getElementById('answer-view').onchange();
await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[0].limit===25&&calls[0].offset===0,'History is unbounded');
doc.getElementById('answer-pagination').lastChild.onclick();await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[1].offset===25,'Next page did not advance');
doc.getElementById('answer-search').value='Example';doc.getElementById('answer-search').oninput();await new Promise(resolve=>setTimeout(resolve,0));
assert(calls[2].search==='example'&&calls[2].offset===0,'Search did not reset pagination');
assert(!doc.querySelector('#answer-groups form'),'History offered application writes');
''')
