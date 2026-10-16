"""New workspace controls preserve existing filters and intake flow."""
from test_dispatch_queue_ui import dashboard_check


def test_overview_filters_use_existing_job_semantics():
    dashboard_check(r'''
v.jobs=[{id:'a',company:'Ready',status:'queued'},
 {id:'b',company:'Done',status:'applied'},
 {id:'c',company:'Help',status:'blocked'},
 {id:'d',company:'Canceled',status:'queued',disposition:'canceled'}];
w.draw(v);
assert(doc.getElementById('overview-active').textContent==='2','Canceled or submitted counted as active');
assert(doc.getElementById('overview-submitted').textContent==='1','Submission count incorrect');
doc.querySelector('[data-overview-filter="submitted"]').click();
assert(doc.getElementById('job-filter').value==='submitted','Overview did not apply filter');
assert(doc.querySelectorAll('#queue-rows tr').length===1,'Overview filter did not render');
assert(doc.querySelector('#queue-rows').textContent.includes('Done'),'Wrong overview result');
doc.getElementById('job-detail-toggle').click();
assert(doc.getElementById('jobs-panel').classList.contains('expanded-columns'),'Details toggle failed');
assert(doc.getElementById('job-detail-toggle').getAttribute('aria-pressed')==='true','Details state not announced');
''')


def test_add_job_dialog_keeps_draft_when_dismissed():
    dashboard_check(r'''
const dialog=doc.getElementById('intake-dialog');
dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;};
doc.getElementById('open-intake').click();
assert(dialog.open,'Add job did not open');
doc.getElementById('job-url').value='https://employer.example.test/job/1';
doc.getElementById('close-intake').click();
assert(!dialog.open,'Close did not dismiss');
doc.getElementById('open-intake').click();
assert(doc.getElementById('job-url').value.includes('/job/1'),'Closing lost draft');
''')
