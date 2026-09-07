"""Visible controls remain usable; persisted metadata excludes answer labels."""
import json
import subprocess
from job_applier.managed_hermes_worker import INVENTORY, make_field_metadata


def test_inventory_retains_visible_option_and_navigation_labels():
    harness = r"""
const vm=require('node:vm');
function elem(text,tag,role){return {innerText:text,tagName:tag,id:'',name:'',labels:[],
 getAttribute:k=>k==='role'?role:null,getBoundingClientRect:()=>({width:100,height:20}),
 closest:()=>null};}
const items=[elem('United States','LI','option'),elem('Save and Continue','BUTTON',null)];
const context={window:{},location:{href:'https://example.test/job/1'},
 crypto:require('node:crypto').webcrypto,getComputedStyle:()=>({visibility:'visible'}),
 document:{title:'Fixture',body:{innerText:'Fixture'},querySelector:()=>null,
 querySelectorAll:s=>s.startsWith('input,')?items:[]}};
const result=vm.runInNewContext(SCRIPT,context);
console.log(JSON.stringify(result.items.map(x=>x.label)));
""".replace('SCRIPT', json.dumps(INVENTORY))
    run = subprocess.run(['node.exe', '-e', harness], capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(run.stdout) == ['United States', 'Save and Continue']


def test_option_metadata_does_not_persist_answer_text():
    key, label = make_field_metadata({'tag': 'LI', 'role': 'option', 'label': 'United States'})
    assert label == 'control_option'
    assert 'United States' not in key
