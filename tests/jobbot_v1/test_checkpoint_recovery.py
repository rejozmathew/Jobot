"""Synthetic regressions for the previously untested September 9 checkpoint."""
import asyncio
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from job_applier import browser_controls, workday_fast
from job_applier.simplify_boundary import SimplifyBoundary
from test_workday_fast import Harness, snapshot


@pytest.mark.parametrize('status', ['ready', 'complete', 'needs_review'])
def test_enabled_extension_continue_follows_initial_autofill_before_source_repair(status, monkeypatch):
    observed = snapshot(status)
    observed['controls']['autofill'] = {'enabled': True}
    observed['native']['continue'] = {'enabled': True}
    assert SimplifyBoundary.decide(observed)['action'] == 'autofill'
    observed['autofill_attempted']=True
    assert SimplifyBoundary.decide(observed)['action'] == 'continue'
    harness = Harness([observed])
    runner = harness.runner()

    async def unexpected_source(*args, **kwargs):
        raise AssertionError('Source repair must not intercept enabled Continue')

    monkeypatch.setattr(runner, 'fill_source', unexpected_source)
    asyncio.run(runner.run(seconds=1))
    assert harness.clicks == ['continue']


@pytest.mark.parametrize('step', ['my_information', 'voluntary_disclosures', 'self_identify'])
def test_first_autofill_precedes_manual_repair_and_survives_changed_values(step):
    observed = snapshot(step=step)
    observed['controls'] = {'autofill': {'enabled': True}}
    observed['native']['continue'] = {'enabled': True}
    assert workday_fast.choose(observed, {}) == 'autofill'
    observed['fingerprint'] = 'field-values-changed'
    assert workday_fast.choose(observed, {'autofill_started': True}) == 'native_continue'
    observed['autofill_attempted'] = True
    assert workday_fast.choose(observed, {}) == 'native_continue'


def test_document_replacement_resets_fill_receipt_but_rerender_does_not(monkeypatch):
    observed = snapshot(document_id='first-document')
    harness = Harness([observed])
    runner = harness.runner()
    runner.state.update(document_id='first-document', pages={'my_experience': {'fills': 1}})

    async def current_page(*args):
        return observed

    monkeypatch.setattr(workday_fast, 'observe_page', current_page)
    observed['fingerprint'] = 'rerendered-fields'
    asyncio.run(workday_fast.FastRunner.observe(runner))
    assert runner.state['pages']['my_experience']['fills'] == 1
    observed['document_id'] = 'replacement-document'
    asyncio.run(workday_fast.FastRunner.observe(runner))
    assert runner.state['pages'] == {}


def source_dom(html):
    root = Path(__file__).resolve().parents[2]
    jsdom = root / 'artifacts/jobbot-v1-private/dom-test/node_modules/jsdom'
    if not jsdom.exists():
        pytest.skip('optional jsdom fixture dependency not installed')
    script = r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const dom=new JSDOM(data.html,{url:'https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1/applyManually',runScripts:'outside-only'});
const w=dom.window;
w.HTMLElement.prototype.getBoundingClientRect=function(){return {width:100,height:20,left:0,right:100,top:0,bottom:20}};
const observation=w.eval(data.observe)({page_signature:'fixture'});
const source=w.eval(data.source)({method:'begin'});
const targets=(source.options||[]).map(o=>{
 const e=w.__jobbotWorkdayScope.inventory.get(o.ref);
 return {tag:e.tagName,menu:e.closest('[role="listbox"]')?.id};
});
console.log(JSON.stringify({observation,source,targets}));w.close();
'''
    output = subprocess.run(['node', '-e', script, str(jsdom)],
        input=json.dumps({'html': html, 'observe': workday_fast.WORKDAY_OBSERVE,
                         'source': workday_fast.WORKDAY_SOURCE}),
        capture_output=True, text=True, check=True, timeout=15)
    return json.loads(output.stdout)


@pytest.mark.parametrize('expanded', ['false', 'true'])
def test_selected_source_chip_is_preserved_even_inside_open_prompt(expanded):
    result = source_dom(f'''
<h2>My Information</h2><div data-automation-id="formField-source">
 <label for="source">How did you hear about us? *</label>
 <div role="listbox"><span data-automation-id="selectedItem-21">Hiring event</span>
 <input id="source" role="combobox" aria-expanded="{expanded}" placeholder="Select One">
 </div></div>''')
    field = next(i for i in result['observation']['inventory'] if i['id'] == 'source')
    assert field['present'] and field['selected_value'] == 'Hiring event'
    assert field['question'] == 'How did you hear about us? *'
    assert result['source']['filled'] and result['source']['kind'] == 'done'


def test_source_menu_is_scoped_and_resolves_category_arrow_and_radio_label():
    result = source_dom('''
<h2>My Information</h2><div role="listbox" id="country"><div role="option">Country option</div></div>
<div data-automation-id="formField-source"><label for="source">How did you hear about us?</label>
 <input id="source" role="combobox" aria-controls="source-menu" aria-expanded="true">
</div><div id="source-menu" role="listbox">
 <div role="option">Agency<span data-automation-id="chevronRight"></span></div>
 <label><input type="radio" name="recruiting-source">Hiring event</label>
</div>''')
    assert [(o['label'], o['child']) for o in result['source']['options']] == [
        ('Agency', True), ('Hiring event', False)]
    assert result['targets'] == [
        {'tag': 'SPAN', 'menu': 'source-menu'}, {'tag': 'LABEL', 'menu': 'source-menu'}]


def test_direct_apply_manually_precedes_chat_entry():
    result = source_dom('''<h1>Careers</h1><button>Apply with Chat</button>
<a href="/applyManually">Apply Manually</a><button>Apply</button>''')
    assert result['observation']['native']['apply']['label'] == 'apply manually'
    assert result['observation']['native']['apply']['enabled']


@pytest.mark.parametrize('stale_clicks', [0, 1])
def test_source_traversal_retries_noncommitting_choice_and_follows_offered_leaf(stale_clicks):
    harness = Harness([snapshot()])
    runner = harness.runner()

    class SourcePage:
        def __init__(self):
            self.stage = 'closed'
            self.clicks = []

        async def evaluate_function(self, script, args):
            assert script == workday_fast.WORKDAY_SOURCE
            info = {'found': True, 'filled': self.stage == 'done', 'field_key': 'source'}
            if args['method'] == 'inspect':
                return info
            if self.stage == 'closed':
                return dict(info, kind='open', ref='source')
            if self.stage == 'parent':
                return dict(info, kind='options', signature='parent', options=[
                    {'ref': 'agency', 'label': 'Agency', 'child': True}])
            if self.stage == 'leaf':
                return dict(info, kind='options', signature='leaf', options=[
                    {'ref': 'event', 'label': 'Hiring event', 'child': False}])
            return dict(info, kind='done', value='Hiring event')

        async def click_observed(self, script, args):
            self.clicks.append(args['ref'])
            if args['ref'] == 'source':
                self.stage = 'parent'
            elif args['ref'] == 'agency':
                if self.clicks.count('agency') > stale_clicks:
                    self.stage = 'leaf'
            elif args['ref'] == 'event':
                self.stage = 'done'
            return {'clicked': True}

    runner.page = SourcePage()
    result = asyncio.run(runner.fill_source(snapshot(), {}, 20))
    assert result['committed'] and result['value'] == 'Hiring event'
    assert runner.page.clicks == ['source'] + ['agency'] * (stale_clicks + 1) + ['event']


def test_reload_waits_through_loading_then_continues_without_another_refresh(monkeypatch):
    states = [snapshot('missing'), snapshot('ready')]
    states[0]['controls'] = {}

    async def observe(*args):
        return states.pop(0)

    monkeypatch.setattr(browser_controls, 'observe', observe)
    result = asyncio.run(browser_controls.wait_for_page_recovery(None, Harness([]).package, seconds=2))
    assert result['status'] == 'recovered'
    assert result['screen']['step'] == 'my_experience'
    assert 'Do not reload or restart again' in result['instruction']


def test_reload_cancellation_remains_serialized_and_cannot_bypass_pending_submit(tmp_path):
    from job_applier.managed import ProtocolError
    from test_local_sessions import setup, reserve, connect, own
    service, asset, jobs, *_ = setup(tmp_path)
    session = connect(service, reserve(service, asset, jobs))
    owner = own(service, session)
    service.writer_state(**owner, state='unknown')
    service.action_start(**owner, action_id='reload', tool_name='local_browser.reload')
    with pytest.raises(ProtocolError, match='browser_writer_busy'):
        service.action_start(**owner, action_id='overlapping', tool_name='local_browser.reload')
    assert service.attempt(owner['attempt_id'])['writer_state'] == 'unknown'
    service.action_end(**owner, action_id='reload', status='success')
    service.writer_state(**owner, state='idle')
    service.submission_intent(**owner, evidence='Synthetic submit intent', fixture=True)


def test_real_shared_reload_replaces_document_and_reports_usable_form(tmp_path):
    from job_applier.application_runtime import browser_action
    from test_embedded_forms import fixture_browser

    async def check():
        async with fixture_browser(tmp_path, mode='top') as (page, package, submissions):
            await page.evaluate('window.beforeReload=true')
            calls = []
            client = SimpleNamespace(call=lambda operation, **params: calls.append((operation, params)) or {})
            config = {'cdp_url': page.fixture_endpoint, 'browser_mode': 'headless'}
            owner = {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1}
            result = await asyncio.to_thread(browser_action, config, client, owner, package,
                                            page.target_id, {'method': 'reload'})
            assert result['document_replaced']
            assert result['recovery']['status'] == 'recovered'
            assert await page.evaluate('window.beforeReload===undefined')
            assert [p['state'] for op, p in calls if op == 'writer_state'] == ['unknown', 'idle']
            assert not submissions

    asyncio.run(check())
