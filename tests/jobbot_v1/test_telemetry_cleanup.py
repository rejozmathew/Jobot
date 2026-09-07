import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import pytest

from job_applier.managed_hermes_worker import (
    ApplicationTool, make_field_metadata, confirmation_verified, run_request
)
from job_applier.managed import Service
from job_applier.managed_shared import ProtocolError


def test_make_field_metadata_stable_and_safe():
    # 1. id first
    k1, l1 = make_field_metadata({'id': 'first_name', 'label': 'First Name *'})
    assert k1 == 'first_name'
    assert l1 == 'First Name *'

    # 2. data-automation-id fallback
    k2, l2 = make_field_metadata({'automation_id': 'postal-code', 'label': 'Zip Code'})
    assert k2 == 'postal-code'
    assert l2 == 'Zip Code'

    # 3. Invalid characters or missing id uses short hash fallback matching regex
    k3, l3 = make_field_metadata({'label': 'What is your favorite color? (required)'})
    import re
    assert re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', k3)
    assert k3.startswith('f_')
    assert 'What' in l3

    # 4. No values or secrets in key/label
    k4, l4 = make_field_metadata({'id': 'pwd', 'value': 'secret_pass123', 'label': 'Password'})
    assert 'secret_pass123' not in k4
    assert 'secret_pass123' not in l4


def test_field_telemetry_attribution_and_no_secrets(tmp_path, monkeypatch):
    """Field action emits field_context before action, attributes time, and emits field_verified on change."""
    events_recorded = []
    actions_recorded = []

    class DummyClient:
        def call(self, op, **kw):
            if op == 'event':
                events_recorded.append(kw)
            elif op == 'action_start':
                actions_recorded.append(('start', kw))
            elif op == 'action_end':
                actions_recorded.append(('end', kw))
            return {'control': 'running', 'quiescent': True}

    class DummyAdapter:
        def __init__(self, c): self.client = c

    class DummyController:
        def __init__(self, c):
            self.adapters = {'s1': DummyAdapter(c)}
        def handle(self, req, session_id=None):
            return json.dumps({})

    ctrl = DummyController(DummyClient())
    app = ApplicationTool(ctrl, 's1', 'run-1', {'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222'})
    app.context = {'attempt_id': 1, 'worker_id': 'w1', 'fence': 1}
    app.package = {'job': {'url': 'https://example.test/job/1'}}
    app.target = 'tab-1'

    initial_items = [
        {'ref': 'ref-1', 'id': 'first_name', 'tag': 'INPUT', 'type': 'text', 'label': 'First Name', 'value': ''}
    ]
    updated_items = [
        {'ref': 'ref-1', 'id': 'first_name', 'tag': 'INPUT', 'type': 'text', 'label': 'First Name', 'value': 'Jane'}
    ]
    eval_count = 0

    class DummySession:
        async def call(self, method, params=None): return {}

    class DummyPage:
        def __init__(self): self._session = DummySession()
        async def evaluate(self, script, args=None):
            nonlocal eval_count
            if script == 'location.href': return 'https://example.test/job/1'
            eval_count += 1
            items = updated_items if eval_count > 1 else initial_items
            return {'url': 'https://example.test/job/1', 'items': items, 'errors': [], 'text': 'form'}

    class DummyBrowser:
        async def get_current_page(self): return DummyPage()
        async def close(self): pass

    async def dummy_connect(): return DummyBrowser()
    async def no_sleep(s=0): pass
    monkeypatch.setattr(app, 'connect', dummy_connect)
    monkeypatch.setattr(asyncio, 'sleep', no_sleep)

    async def _test():
        await app.inventory(DummyPage())
        assert app._last_inventory is not None

        res = await app.operate({'operation': 'fill', 'ref': 'ref-1', 'text': 'Jane'})
        assert res is not None

        # Check field_context was emitted BEFORE action_start
        fc = [e for e in events_recorded if e.get('event_type') == 'field_context']
        assert len(fc) >= 1
        assert fc[0]['payload']['field'] == 'first_name'
        assert fc[0]['payload']['page'] == 'tab-1'

        # Check action_start and action_end wrapped the action
        assert any(a[0] == 'start' and a[1]['tool_name'] == 'form_fill' for a in actions_recorded)
        assert any(a[0] == 'end' and a[1]['status'] == 'success' for a in actions_recorded)

        # Check field_verified was emitted on actual committed value change
        fv = [e for e in events_recorded if e.get('event_type') == 'field_verified']
        assert len(fv) >= 1
        assert fv[0]['payload']['field'] == 'first_name'
        # Crucial: verify raw user input 'Jane' is NOT leaked in event evidence
        assert 'Jane' not in fv[0]['payload']['evidence']

    asyncio.run(_test())


def test_field_unchanged_emits_structured_recovery(tmp_path, monkeypatch):
    """When a field action does not produce committed change, a structured recovery event is emitted."""
    events_recorded = []

    class DummyClient:
        def call(self, op, **kw):
            if op == 'event': events_recorded.append(kw)
            return {'control': 'running', 'quiescent': True}

    class DummyAdapter:
        def __init__(self, c): self.client = c

    class DummyController:
        def __init__(self, c): self.adapters = {'s1': DummyAdapter(c)}
        def handle(self, req, session_id=None): return json.dumps({})

    ctrl = DummyController(DummyClient())
    app = ApplicationTool(ctrl, 's1', 'run-1', {'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222'})
    app.context = {'attempt_id': 1, 'worker_id': 'w1', 'fence': 1}
    app.package = {'job': {'url': 'https://example.test/job/1'}}
    app.target = 'tab-1'

    static_items = [
        {'ref': 'ref-1', 'id': 'city', 'tag': 'INPUT', 'type': 'text', 'label': 'City', 'value': ''}
    ]

    class DummySession:
        async def call(self, method, params=None): return {}

    class DummyPage:
        def __init__(self): self._session = DummySession()
        async def evaluate(self, script, args=None):
            if script == 'location.href': return 'https://example.test/job/1'
            return {'url': 'https://example.test/job/1', 'items': static_items, 'errors': [], 'text': 'form'}

    class DummyBrowser:
        async def get_current_page(self): return DummyPage()
        async def close(self): pass

    async def dummy_connect(): return DummyBrowser()
    async def no_sleep(s=0): pass
    monkeypatch.setattr(app, 'connect', dummy_connect)
    monkeypatch.setattr(asyncio, 'sleep', no_sleep)

    async def _test():
        await app.inventory(DummyPage())
        await app.operate({'operation': 'fill', 'ref': 'ref-1', 'text': 'Denver'})

        rec = [e for e in events_recorded if e.get('event_type') == 'recovery']
        assert len(rec) >= 1
        p = rec[0]['payload']
        assert p['field_key'] == 'city'
        assert p['source'] == 'native'
        assert p['status'] == 'unresolved'
        assert p['category'] == 'field_unchanged'
        assert 'Denver' not in str(p)

    asyncio.run(_test())


def test_attempt_report_aggregations_and_historical_unknown(tmp_path):
    """attempt_report provides per-field telemetry, Simplify aggregation, and preserves unknown for historical."""
    s = Service.create(tmp_path / 'report_test.db', instance_id='inst-rep')
    s.identity(identity_id='c1', person_key='p1', email='cand@example.test', profile={'facts': {}})
    job = s.intake(url='https://jobs.example.test/1', source_id='j1')
    s.eligibility(job['id'], 'ready', reason='approved')
    run = s.request_run(request_id='r1', job_ids=[job['id']], identity_id='c1', browser_profile='p1')
    s.accept_run(run['id'], worker_id='w1', session_id='s1', capabilities={
        'protocol': 1, 'skill_version': 'v1', 'provider': 'fixture',
        'model': 'fixture', 'telemetry': True, 'browser_profile': 'p1'
    })
    attempt = s.claim(run['id'], worker_id='w1')
    aid = attempt['id']

    # 1. Add native field action events
    s.event(aid, worker_id='w1', fence=1, event_id='ev-fc-1', event_type='field_context',
            observed_at=s.now(), payload={'page': 'tab-1', 'field': 'first_name', 'category': 'field'})
    act1 = s.action_start(aid, worker_id='w1', fence=1, action_id='act-1', tool_name='form_fill')
    s.action_end(aid, worker_id='w1', fence=1, action_id='act-1', status='success', duration_seconds=2.5)
    s.event(aid, worker_id='w1', fence=1, event_id='ev-fv-1', event_type='field_verified',
            observed_at=s.now(), payload={'page': 'tab-1', 'field': 'first_name', 'evidence': 'verified change'})

    # 2. Add Simplify run event
    s.event(aid, worker_id='w1', fence=1, event_id='ev-simp-1', event_type='recovery',
            observed_at=s.now(), payload={
                'category': 'needs_review', 'source': 'Simplify', 'fallback_reason': 'residual_fields_remain',
                'status': 'unresolved', 'residual_fields': ['ssn', 'custom_question'],
                'elapsed_seconds': 4.0, 'field_attribution': 'unknown'
            })

    report = s.attempt_report(aid)
    assert 'fields' in report, "attempt_report must include 'fields' aggregation"
    assert 'simplify' in report, "attempt_report must include 'simplify' aggregation"
    assert 'problems' in report, "attempt_report must include 'problems' rows"

    # Verify native field stats
    f_stat = report['fields']['first_name']
    assert f_stat['elapsed_seconds'] == 2.5
    assert f_stat['action_count'] == 1
    assert f_stat['verified'] is True
    assert f_stat['attribution'] == 'native'

    # Verify Simplify stats (aggregate without fabricated per-field timing)
    simp = report['simplify']
    assert simp['runs_count'] >= 1
    assert simp['total_duration_seconds'] >= 4.0
    assert 'residual_fields_remain' in simp['fallback_reasons']

    # Historical field with no tool events must remain unknown/None, not fabricated
    assert 'historical_field' not in report['fields'] or report['fields']['historical_field']['elapsed_seconds'] is None


def test_success_evidence_saved_before_tab_close_and_only_owned_target_closed(tmp_path, monkeypatch):
    """Durable receipt is saved before closeTarget; only owned target is closed while unrelated tabs remain."""
    calls = []
    target_state_calls = []

    class DummyClient:
        def call(self, op, **kw):
            calls.append((op, kw))
            if op == 'target_state':
                target_state_calls.append(kw)
            return {'control': 'running', 'quiescent': True}

    class DummyAdapter:
        def __init__(self, c): self.client = c

    class DummyController:
        def __init__(self, c): self.adapters = {'s1': DummyAdapter(c)}
        def handle(self, req, session_id=None):
            calls.append(('protocol_' + req['operation'], req))
            return json.dumps({})

    spool = tmp_path / 'spool_test'
    spool.mkdir()
    ctrl = DummyController(DummyClient())
    app = ApplicationTool(ctrl, 's1', 'run-1', {
        'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222', 'spool_dir': str(spool),
        'model': 'gpt-5.6-luna', 'reasoning_effort': 'low'
    })
    app.context = {'attempt_id': 99, 'worker_id': 'w1', 'fence': 1}
    app.package = {'job': {'url': 'https://example.test/job/1'}}
    app.target = 'tab-owned'

    browser_targets = [
        {'id': 'tab-owned', 'targetId': 'tab-owned', 'type': 'page'},
        {'id': 'tab-user-1', 'targetId': 'tab-user-1', 'type': 'page'},
        {'id': 'tab-user-2', 'targetId': 'tab-user-2', 'type': 'page'}
    ]

    receipt_existed_before_close = False

    class DummySession:
        async def close(self): pass
        async def call(self, method, params=None):
            nonlocal receipt_existed_before_close
            params = params or {}
            if method == 'Target.closeTarget':
                r_path = spool / 'submission-receipt-99.json'
                if r_path.exists():
                    receipt_existed_before_close = True
                assert params.get('targetId') == 'tab-owned'
                browser_targets[:] = [t for t in browser_targets if t['id'] != 'tab-owned']
                return {'success': True}
            elif method == 'Target.getTargets':
                return {'targetInfos': list(browser_targets)}
            return {}

    class DummyPage:
        def __init__(self): self._session = DummySession()
        async def evaluate(self, script, args=None):
            return {
                'url': 'https://example.test/job/1/confirmation',
                'items': [],
                'errors': [],
                'text': 'Thank you for your application! Application has been successfully submitted.'
            }

    class DummyBrowser:
        async def get_current_page(self): return DummyPage()
        async def close(self): pass

    async def dummy_connect(): return DummyBrowser()
    monkeypatch.setattr(app, 'connect', dummy_connect)

    async def _test():
        async def control_session(): return DummySession()
        monkeypatch.setattr(app, 'connect_control', control_session)
        receipt = await app.confirm(DummyPage())
        assert receipt['outcome'] == 'applied'
        assert receipt_existed_before_close is True, "Durable receipt must be written BEFORE closing tab"

        # Verify only tab-owned was closed and unrelated tabs remain
        remaining_ids = {t['id'] for t in browser_targets}
        assert 'tab-owned' not in remaining_ids
        assert 'tab-user-1' in remaining_ids
        assert 'tab-user-2' in remaining_ids

        # Verify target_state was recorded as 'closed' BEFORE finish protocol call
        ts_closed = [c for c in target_state_calls if c.get('state') == 'closed']
        assert len(ts_closed) >= 1
        assert ts_closed[0]['target_id'] == 'tab-owned'

        # Finish was called with quiescent=True
        finish_calls = [c for c in calls if c[0] == 'protocol_finish']
        assert len(finish_calls) == 1
        assert finish_calls[0][1]['parameters']['outcome'] == 'applied'
        assert finish_calls[0][1]['parameters']['quiescent'] is True

    asyncio.run(_test())


def test_close_failure_and_stale_fence_do_not_claim_closed_or_success(tmp_path, monkeypatch):
    """A receipt survives cleanup failure without releasing the owner or closing unrelated tabs."""
    target_state_calls = []
    protocol_calls = []

    class DummyClient:
        def call(self, op, **kw):
            if op == 'target_state':
                if kw.get('worker_id') == 'stale_worker':
                    raise ProtocolError('stale_owner')
                target_state_calls.append(kw)
            return {'control': 'running', 'quiescent': True}

    class DummyAdapter:
        def __init__(self, c): self.client = c

    class DummyController:
        def __init__(self, c): self.adapters = {'s1': DummyAdapter(c)}
        def handle(self, req, session_id=None):
            protocol_calls.append(req)
            return json.dumps({})

    spool = tmp_path / 'spool_fail'
    spool.mkdir()
    ctrl = DummyController(DummyClient())
    app = ApplicationTool(ctrl, 's1', 'run-1', {
        'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222', 'spool_dir': str(spool),
        'model': 'gpt-5.6-luna', 'reasoning_effort': 'low'
    })
    app.context = {'attempt_id': 100, 'worker_id': 'w1', 'fence': 1}
    app.package = {'job': {'url': 'https://example.test/job/1'}}
    app.target = 'tab-owned'

    class FailingSession:
        async def close(self): pass
        async def call(self, method, params=None):
            if method == 'Target.closeTarget':
                return {'success': False} # Close failed!
            return {}

    class DummyPage:
        def __init__(self): self._session = FailingSession()
        async def evaluate(self, script, args=None):
            return {
                'url': 'https://example.test/job/1/confirmation',
                'items': [],
                'errors': [],
                'text': 'Thank you for your application!'
            }

    class DummyBrowser:
        async def get_current_page(self): return DummyPage()
        async def close(self): pass

    async def dummy_connect(): return DummyBrowser()
    monkeypatch.setattr(app, 'connect', dummy_connect)

    async def _test():
        async def control_session(): return FailingSession()
        monkeypatch.setattr(app, 'connect_control', control_session)
        res = await app.confirm(DummyPage())
        # Employer truth survives cleanup failure, but the worker is not finished.
        assert res.get('outcome') == 'applied'
        assert not app.finished
        assert res.get('cleanup_status') == 'cleanup_pending'

        # target_state must NOT have been marked 'closed'
        assert not any(c.get('state') == 'closed' for c in target_state_calls)

        # Protocol finish must NOT be called with applied
        finish_applied = [c for c in protocol_calls if c.get('operation') == 'finish' and c.get('parameters', {}).get('outcome') == 'applied']
        assert len(finish_applied) == 0

        # Stale ownership must be rejected BEFORE touching CDP or HTTP.
        app.context['worker_id'] = 'stale_worker'
        async def forbidden_connect():
            pytest.fail('Stale worker must not connect to browser')
        monkeypatch.setattr(app, 'connect', forbidden_connect)
        monkeypatch.setattr(app, 'connect_control', forbidden_connect)
        with pytest.raises(ProtocolError, match='stale_owner'):
            await app.close_target()

    asyncio.run(_test())


def test_failure_exception_cleanup_in_run_request(tmp_path, monkeypatch):
    """Worker exit on failure/exception cleans up owned target and classifies attempt outcome."""
    target_state_calls = []
    protocol_calls = []

    class DummyClient:
        def call(self, op, **kw):
            if op == 'target_state': target_state_calls.append(kw)
            return {'control': 'running', 'quiescent': True}

    class DummyAdapter:
        def __init__(self, c): self.client = c

    class DummyController:
        def __init__(self, c): self.adapters = {'s1': DummyAdapter(c)}
        def handle(self, req, session_id=None):
            protocol_calls.append(req)
            return json.dumps({})
        def close(self): pass

    spool = tmp_path / 'spool_exit'
    spool.mkdir()
    ctrl = DummyController(DummyClient())
    app = ApplicationTool(ctrl, 's1', 'run-1', {
        'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222', 'spool_dir': str(spool),
        'model': 'gpt-5.6-luna', 'reasoning_effort': 'low'
    })
    app.context = {'attempt_id': 105, 'worker_id': 'w1', 'fence': 1}
    app.package = {'job': {'url': 'https://example.test/job/1'}}
    app.target = 'tab-owned'
    app.submit_clicked = True  # Clicked but interrupted/failed before confirmation

    class DummySession:
        async def close(self): pass
        async def call(self, method, params=None):
            if method == 'Target.closeTarget': return {'success': True}
            if method == 'Target.getTargets': return {'targetInfos': []}
            return {}

    class DummyPage:
        def __init__(self): self._session = DummySession()

    class DummyBrowser:
        async def get_current_page(self): return DummyPage()
        async def close(self): pass

    async def dummy_connect(): return DummyBrowser()
    monkeypatch.setattr(app, 'connect', dummy_connect)

    async def control_session(): return DummySession()
    monkeypatch.setattr(app, 'connect_control', control_session)
    # Exercise the same shutdown routine run_request invokes on exception.
    status = app.loop.run_until_complete(app.finalize())
    assert status == 'closed'
    assert app.target_closed is True
    assert any(c.get('state') == 'closed' for c in target_state_calls)
    finishes = [c['parameters'] for c in protocol_calls if c['operation'] == 'finish']
    assert finishes[0]['outcome'] == 'submission_unknown'
    assert finishes[0]['quiescent'] is True
    app.loop.close()
