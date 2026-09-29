"""Delayed intermediate navigation stays inside the owned helper observation loop."""
import asyncio
import time

import pytest

from test_form_audit import fixture_html, icims_browser


@pytest.mark.parametrize('reconnect', [False, True])
@pytest.mark.parametrize('incidental', ['optional', 'reorder'])
def test_delayed_profile_advance_keeps_simplify_first_without_duplicate_click(tmp_path, monkeypatch, reconnect, incidental):
    import test_embedded_forms as fixture
    from job_applier import icims_fast
    from job_applier.cdp_client import CDPBrowser
    # Slow server response, followed by an independently available Simplify pass.
    update = ("document.querySelector('#preferred-name').value='background update';"
              "document.querySelector('form').insertAdjacentHTML('beforeend','<button type=button>Help</button>');"
              if incidental == 'optional' else
              "document.querySelector('#first-name').closest('.field').before(document.querySelector('#last-name').closest('.field'));")
    html = fixture_html().replace('counters.profileSubmits++; screening();',
        'counters.profileSubmits++; setTimeout(()=>{' + update + '},200);'
        "setTimeout(() => {screening(); fixture.setSimplify('needs_review');}, 1800);")
    monkeypatch.setattr(fixture, 'FORM_HTML', html)

    async def run():
        async with icims_browser(tmp_path) as (page, package, _):
            await page.evaluate("""fixture.autofillDelay=50;
                document.querySelector('#password').value='synthetic';
                document.querySelector('#confirmation').value='synthetic';
                document.querySelector('#server-error').remove();""")
            package['attempt']['settings_json'] = {'submission_mode': 'review'}
            calls = []
            def call(op, **params):
                calls.append(op)
                if op == 'heartbeat': return {'control': 'running'}
                if op == 'browser_observe': return {'native_takeover_authorized': True, 'observation': {}}
                return {}
            def runner(current):
                r = icims_fast.IcimsRunner(current, call, package,
                    {'attempt_id': 1, 'worker_id': 'test', 'fence': 1},
                    {'cdp_url': page.fixture_endpoint, 'spool_dir': str(tmp_path / 'spool')}, page.target_id)
                original_gate = r.gate
                async def gate():
                    ready = await original_gate(); r.documents = None; return ready
                r.gate = gate
                return r
            first = runner(page)
            original_click = icims_fast.click_control
            if reconnect:
                async def expire_after_click(*args, **kwargs):
                    result = await original_click(*args, **kwargs)
                    first.deadline = time.monotonic()
                    return result
                monkeypatch.setattr(icims_fast, 'click_control', expire_after_click)
            result = await first.run(20)
            if reconnect:
                assert result['reason'] == 'call_slice_complete', result
                assert result['actions']['stage_advance'] == 1, result
                monkeypatch.setattr(icims_fast, 'click_control', original_click)
                browser = await CDPBrowser.connect(page.fixture_endpoint, target_id=page.target_id, expected_mode='headless')
                try:
                    result = await runner(await browser.get_current_page()).run(20)
                finally:
                    await browser.close()
            assert result['status'] == 'questions_required', result
            assert len(result['questions']) == 2, result
            counters = await page.evaluate('fixture.counters')
            assert counters['profileSubmits'] == 1 and counters['finalSubmits'] == 0
            assert counters['autofillClicks'] == 2, result
            assert result['actions']['repair_fields'] == 0
            # The new step must finish its Simplify pass before residual inspection.
            new_stage = result['trace'].index('audit:screening')
            settled = result['trace'].index('simplify_settlement', new_stage)
            assert 'residual_audit' not in result['trace'][new_stage:settled]
            assert 'finish' not in calls
    asyncio.run(run())


@pytest.mark.parametrize('outcome', ['stop', 'validation', 'unchanged'])
def test_pending_advance_still_observes_stop_validation_and_allows_later_retry(tmp_path, monkeypatch, outcome):
    import test_embedded_forms as fixture
    from job_applier import icims_fast
    response = ("setTimeout(()=>document.querySelector('#first-name').value='', 400);"
                if outcome == 'validation' else '')
    monkeypatch.setattr(fixture, 'FORM_HTML', fixture_html().replace(
        'counters.profileSubmits++; screening();', 'counters.profileSubmits++;' + response))

    async def run():
        async with icims_browser(tmp_path) as (page, package, _):
            await page.evaluate("""fixture.autofillDelay=50;
                document.querySelector('#password').value='synthetic';
                document.querySelector('#confirmation').value='synthetic';
                document.querySelector('#server-error').remove();""")
            state = {'control': 'running'}; calls = []
            def call(op, **params):
                calls.append(op)
                if op == 'heartbeat': return state
                if op == 'browser_observe': return {'native_takeover_authorized': True, 'observation': {}}
                return {}
            def runner():
                r = icims_fast.IcimsRunner(page, call, package,
                    {'attempt_id': 1, 'worker_id': 'test', 'fence': 1},
                    {'cdp_url': page.fixture_endpoint, 'spool_dir': str(tmp_path / 'spool')}, page.target_id)
                original_gate = r.gate
                async def gate():
                    ready = await original_gate(); r.documents = None; return ready
                r.gate = gate
                return r
            if outcome == 'stop':
                original_click = icims_fast.click_control
                async def stop_after_click(*args, **kwargs):
                    result = await original_click(*args, **kwargs)
                    state['control'] = 'stop_requested'
                    return result
                monkeypatch.setattr(icims_fast, 'click_control', stop_after_click)
            result = await runner().run(15)
            assert await page.evaluate('fixture.counters.profileSubmits') == 1
            assert result['actions']['stage_advance'] == 1
            if outcome == 'stop':
                assert result['status'] == 'stopped' and result['reason'] == 'stop_requested', result
            elif outcome == 'validation':
                assert result['status'] == 'questions_required', result
                assert len(result['questions']) == 1
                assert result['questions'][0]['field'] == 'first-name'
            else:
                assert result['reason'] == 'unchanged_after_action', result
                assert result['advance_observation']['wait_seconds'] >= 5
                assert await runner().advance_receipt() is None
                # The observation receipt must not turn into a permanent retry veto.
                retried = await runner().run(.8)
                assert retried['reason'] == 'call_slice_complete', retried
                assert await page.evaluate('fixture.counters.profileSubmits') == 2
            assert 'finish' not in calls
    asyncio.run(run())
