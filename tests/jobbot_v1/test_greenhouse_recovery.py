"""Synthetic Greenhouse/shared recovery coverage; no private or live application data."""
import asyncio
import json
from pathlib import Path
import subprocess

import pytest

from job_applier import browser_controls


def form_dom(html, operations=None):
    root = Path(__file__).resolve().parents[2]
    jsdom = root / 'artifacts/jobbot-v1-private/dom-test/node_modules/jsdom'
    if not jsdom.exists():
        pytest.skip('optional jsdom fixture dependency not installed')
    script = r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(data.html,{url:'https://boards.greenhouse.io/example/jobs/12345',runScripts:'outside-only'}).window;
w.HTMLElement.prototype.getClientRects=function(){return this.hidden?[]:[{width:100,height:20}]};
const run=w.eval(data.form), observation=run({method:'observe',page_signature:'fixture'});
const results=(data.operations||[]).map(args=>run(args));
console.log(JSON.stringify({observation,results}));w.close();
'''
    result = subprocess.run(['node', '-e', script, str(jsdom)], input=json.dumps({
        'html': html, 'form': browser_controls.FORM, 'operations': operations or []}),
        capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


def widget(*, expanded='false', selection='Option B', value=''):
    return f'''<label for="veteran">Veteran status *</label>
<div class="select__control"><div class="select__value-container">
<div class="select__single-value">{selection}</div>
<div class="select__input-container"><input id="veteran" role="combobox"
aria-expanded="{expanded}" aria-controls="choices" value="{value}"></div></div></div>
<div role="listbox" id="choices"><div role="option" aria-selected="true">Option A</div></div>'''


@pytest.mark.parametrize('expanded', ['false', 'true'])
def test_separate_selected_label_agrees_across_inventory_inspect_question_and_answers(expanded):
    output = form_dom(widget(expanded=expanded), [
        {'method': 'inspect', 'selector': '#veteran'},
        {'method': 'question', 'selector': '#veteran'},
        {'method': 'verify_select', 'selector': '#veteran', 'value': 'b', 'label': 'Option B'},
        {'method': 'answers', 'page': 'voluntary_disclosures'},
    ])
    field = output['observation']['inventory'][0]
    assert field['present'] and field['selected_value'] == 'Option B'
    inspect, question, verify, answers = output['results']
    assert inspect['value'] == 'Option B'
    assert question['answered'] and verify['committed']
    assert answers['answers'][0]['answer'] == 'Option B'


def test_typed_filter_and_highlighted_option_are_not_committed_answers():
    output = form_dom(widget(selection='', value='Option A', expanded='true'), [
        {'method': 'question', 'selector': '#veteran'},
        {'method': 'verify_select', 'selector': '#veteran', 'value': 'Option A', 'label': 'Option A'},
        {'method': 'answers', 'page': 'voluntary_disclosures'},
    ])
    assert not output['observation']['inventory'][0]['present']
    assert not output['results'][0]['answered']
    assert not output['results'][1]['committed']
    assert output['results'][2]['answers'] == []


def test_another_widget_selected_label_does_not_answer_empty_widget():
    html = widget(selection='') + '''<div class="select__control">
<span class="select__single-value">Option B</span><input role="combobox" aria-label="Disability"></div>'''
    output = form_dom(html)
    assert not output['observation']['inventory'][0]['present']


class SelectionPage:
    def __init__(self, *, selected='', expanded='false', commit_after=1, actual='Option B'):
        self.selected, self.expanded = selected, expanded
        self.commit_after, self.actual = commit_after, actual
        self.clicks, self.verifications = [], 0

    async def evaluate(self, script):
        return 'https://boards.greenhouse.io/example/jobs/12345'

    async def evaluate_function(self, script, args):
        method = args['method']
        if method == 'inspect':
            return {'tag': 'INPUT', 'role': 'combobox', 'expanded': self.expanded,
                    'value': self.selected, 'label': self.selected, 'selected_value': self.selected}
        if method == 'focus':
            return {'committed': True}
        if method == 'select_options':
            return {'options': [{'ref': 'b', 'label': 'Option B', 'value': 'b', 'enabled': True}]}
        if method == 'verify_select':
            self.verifications += 1
            self.selected = self.actual if self.verifications >= self.commit_after else ''
            return {'committed': self.selected == args['label'], 'value': self.selected, 'label': self.selected}
        raise AssertionError(method)

    async def click_observed(self, script, args):
        self.clicks.append(args['ref'])
        return {'clicked': True, 'execution': 'executed'}

    async def press_key(self, key):
        self.clicks.append(key)


def test_already_selected_open_widget_is_not_toggled():
    page = SelectionPage(selected='Option B', expanded='true')
    result = asyncio.run(browser_controls.form_action(page, {'method': 'select', 'ref': 'control', 'label': 'Option B'}))
    assert result['committed'] and result['unchanged'] and page.clicks == []


def test_delayed_commit_is_read_back_until_stable():
    page = SelectionPage(commit_after=3)
    result = asyncio.run(browser_controls.form_action(page, {'method': 'select', 'ref': 'control', 'label': 'Option B'}))
    assert result['committed'] and page.verifications >= 4
    assert page.clicks == ['control', 'b']


def test_wrong_keyboard_option_reports_execution_separately_from_answer():
    page = SelectionPage(actual='Option A')
    result = asyncio.run(browser_controls.form_action(page, {
        'method': 'press', 'ref': 'control', 'key': 'Enter', 'label': 'Option B'}))
    assert result['pressed'] and result['execution'] == 'executed'
    assert result['committed'] is False and result['reason'] == 'selection_mismatch'
    assert result['label'] == 'Option A' and result['options'][0]['label'] == 'Option B'


def test_native_select_still_requires_exact_label_when_values_are_duplicated():
    result = form_dom('''<label for="s">Choice</label><select id="s">
<option value="same">Option A</option><option value="same">Option B</option></select>''', [
        {'method': 'verify_select', 'selector': '#s', 'value': 'same', 'label': 'Option B'}])
    assert result['results'][0]['committed'] is False


@pytest.mark.parametrize('mode',['top','cross'])
def test_real_delayed_rerender_commits_exact_option_in_its_own_widget(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    html='''<label for="veteran">Veteran status</label><div id="widget" class="select__control">
<span class="select__single-value"></span><input id="veteran" role="combobox" aria-controls="choices" aria-expanded="false"></div>
<div role="listbox" id="choices" hidden><div tabindex="0" role="option" data-value="b">Option B</div></div>
<div role="listbox" id="country"><div role="option">Option B</div></div>
<script>veteran.onclick=e=>{if(e.isTrusted){choices.hidden=false;veteran.setAttribute('aria-expanded','true')}};
choices.onclick=e=>{if(!e.isTrusted)return;setTimeout(()=>{widget.innerHTML='<span class="select__single-value">Option B</span><input id="veteran" role="combobox" aria-controls="choices" aria-expanded="false">';choices.hidden=true},250)};
</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,submissions):
            observed=await browser_controls.observe(page,package)
            field=next(f for f in observed['inventory'] if f.get('label')=='Veteran status')
            result=await browser_controls.form_action(page,{'method':'select','ref':field['ref'],'label':'Option B'})
            assert result['committed'] and result['label']=='Option B',result
            fresh=await browser_controls.observe(page,package)
            assert next(f for f in fresh['inventory'] if f.get('label')=='Veteran status')['present']
            assert submissions==[]
    asyncio.run(run())
