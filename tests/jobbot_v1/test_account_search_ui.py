"""Portal search uses synthetic accounts and the shipped dashboard."""
from test_dispatch_queue_ui import dashboard_check


def test_portal_search_preserves_filter_and_correct_account_actions():
    dashboard_check(r'''
w.noRefresh();
const accounts=[
 {id:1,namespace:'acme.wd5.myworkdayjobs.com',email:'first@example.test',identity_id:'first'},
 {id:2,namespace:'careers.birch.test',email:'second@example.test',identity_id:'second',password_editable:true},
 {id:3,portal_key:'legacy.cedar.test'},
 {id:4,company_key:'Delta'}];
const data={accounts,runs:[{id:'history-fixture',state:'finished'}]};
w.drawAccounts(data);
const search=doc.getElementById('account-search'),count=doc.getElementById('account-search-count');
assert(search&&search.type==='search','Portal search missing');
const rows=()=>[...doc.querySelectorAll('#account-rows tr')];
function query(text){search.value=text;search.dispatchEvent(new w.Event('input'));}
assert(rows().length===4&&count.textContent==='4 of 4 accounts','Initial account count incorrect');
query('  BIRCH  ');
assert(rows().length===1&&rows()[0].cells[0].textContent==='careers.birch.test','Site search must ignore case and surrounding whitespace');
assert(count.textContent==='1 of 4 accounts','Filtered count incorrect');
search.focus();w.drawAccounts(data);
assert(search.value==='  BIRCH  '&&doc.activeElement===search&&rows().length===1,'Refresh lost search or focus');
const dialog=doc.getElementById('portal-password-dialog');dialog.showModal=()=>{dialog.open=true;};
dialog.close=()=>{dialog.open=false;dialog.dispatchEvent(new w.Event('close'));};
rows()[0].querySelector('button').click();
assert(doc.getElementById('portal-password-account').textContent==='careers.birch.test · second@example.test','Filtered action targets wrong account');
doc.getElementById('close-portal-password').click();
for(const [term,expected] of [['first@example','acme.wd5.myworkdayjobs.com'],['cedar','legacy.cedar.test'],['delta','Delta']]){
 query(term);assert(rows().length===1&&rows()[0].cells[0].textContent===expected,'Search missed identity or legacy site: '+term);
}
query('no-such-site');
assert(rows().length===1&&rows()[0].textContent.includes('No portal accounts match')&&rows()[0].cells[0].colSpan===6,'No-match message missing');
assert(count.textContent==='0 of 4 accounts','Zero-match count incorrect');
assert(doc.getElementById('history').textContent.includes('history-fixture'),'Search changed run history');
doc.getElementById('account-search-clear').click();
assert(search.value===''&&rows().length===4&&doc.activeElement===search,'Clear must restore accounts and focus search');
query('  ');assert(rows().length===4,'Whitespace should show all accounts');
w.drawAccounts({accounts:[],runs:[]});
assert(rows()[0].textContent.includes('No tracked portal accounts yet')&&count.textContent==='0 of 0 accounts','Empty ledger message missing');
''')
