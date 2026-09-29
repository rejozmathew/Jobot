"""A malformed control must not discard the rest of an owned residual batch."""
import asyncio
import json

import pytest

from test_greenhouse_batch import batch_html, batch_profile


@pytest.mark.parametrize('control', [
    '<input id="unlabelled">',
    '<input id="unlabelled" value="synthetic-existing-value">',
    '<label for="unlabelled">Optional note</label><input id="unlabelled" name="' + 'x' * 501 + '">',
    '<label for="unlabelled">' + 'x' * 4001 + '</label><input id="unlabelled">',
], ids=['unlabelled', 'populated', 'long_identity', 'long_question'])
def test_optional_question_metadata_does_not_abort_later_approved_fields(tmp_path, monkeypatch, control):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    monkeypatch.setattr(fixture, 'FORM_HTML', batch_html().replace('<form>', '<form>' + control))

    async def run():
        async with fixture.fixture_browser(tmp_path, mode='top') as (page, package, submissions):
            package['attempt'].update(profile_json=batch_profile(), settings_json={'submission_mode': 'review'})
            ledger = fixture.SubmissionLedger()
            def runner():
                return GreenhouseRunner(page, ledger.call, package,
                    {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1},
                    {'spool_dir': str(tmp_path / 'spool'), 'cdp_url': page.fixture_endpoint}, page.target_id)
            first = await runner().run(30)
            assert first['status'] == 'ready_for_review', first
            assert first['completed_count'] == 15, first
            assert await page.evaluate('f13.value') == 'approved-13'
            diagnostic = first['question_diagnostics'][0]
            assert diagnostic['reason'] == 'invalid_question' and not diagnostic['needs_recovery']
            assert 'synthetic-existing-value' not in json.dumps(diagnostic)
            second = await runner().run(30)
            assert second['status'] == 'ready_for_review' and second['field_action_count'] == 0, second
            assert submissions == []
    asyncio.run(run())


@pytest.mark.parametrize('control', [
    '<input id="unlabelled" required>',
    '<input id="unlabelled" aria-invalid="true" value="synthetic-rejected-value">',
])
@pytest.mark.parametrize('mode', ['top', 'cross'])
def test_required_or_rejected_unreadable_question_returns_scoped_recovery_after_batch(tmp_path, monkeypatch, control, mode):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    # An error midway through filling must preserve earlier work and complete later controls.
    monkeypatch.setattr(fixture, 'FORM_HTML', batch_html().replace('<label for="f7">', control + '<label for="f7">'))

    async def run():
        async with fixture.fixture_browser(tmp_path, mode=mode) as (page, package, submissions):
            package['attempt'].update(profile_json=batch_profile(), settings_json={'submission_mode': 'submit'})
            ledger = fixture.SubmissionLedger()
            runner = GreenhouseRunner(page, ledger.call, package,
                {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1},
                {'spool_dir': str(tmp_path / 'spool'), 'cdp_url': page.fixture_endpoint}, page.target_id)
            result = await runner.run(30)
            assert result['status'] == 'inspection_required' and result['reason'] == 'control_recovery', result
            assert result['completed_count'] == 15, result
            diagnostic = result['question_diagnostics'][0]
            assert diagnostic['needs_recovery'] and diagnostic['metadata']['question_missing']
            assert diagnostic in result['control_failures']
            assert diagnostic['required'] or diagnostic['invalid']
            assert 'synthetic-rejected-value' not in json.dumps(diagnostic)
            assert not result['questions'] and submissions == []
            assert len(runner.read_journal()) == 15
    asyncio.run(run())


def test_question_recovery_never_swallows_owned_document_failure(tmp_path, monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    from job_applier.browser_frames import FrameUnavailable
    monkeypatch.setattr(fixture, 'FORM_HTML', batch_html())

    async def run():
        async with fixture.fixture_browser(tmp_path, mode='top') as (page, package, submissions):
            package['attempt'].update(profile_json=batch_profile(), settings_json={'submission_mode': 'submit'})
            runner = GreenhouseRunner(page, fixture.SubmissionLedger().call, package,
                {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1},
                {'spool_dir': str(tmp_path / 'spool'), 'cdp_url': page.fixture_endpoint}, page.target_id)
            async def replaced(_field):
                raise FrameUnavailable('application_document_changed')
            monkeypatch.setattr(runner, 'question', replaced)
            result = await runner.run(30)
            assert result['reason'] == 'application_document_changed'
            assert result['field_action_count'] == 0 and submissions == []
    asyncio.run(run())


def test_conditional_required_metadata_is_refreshed_on_rescan(tmp_path, monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    html = batch_html().replace('<form>', '<form><input id="unlabelled">')
    html += '<script>f0.addEventListener("input",()=>unlabelled.required=true)</script>'
    monkeypatch.setattr(fixture, 'FORM_HTML', html)

    async def run():
        async with fixture.fixture_browser(tmp_path, mode='top') as (page, package, submissions):
            package['attempt'].update(profile_json=batch_profile(), settings_json={'submission_mode': 'review'})
            runner = GreenhouseRunner(page, fixture.SubmissionLedger().call, package,
                {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1},
                {'spool_dir': str(tmp_path / 'spool'), 'cdp_url': page.fixture_endpoint}, page.target_id)
            result = await runner.run(30)
            assert result['reason'] == 'control_recovery' and result['completed_count'] == 15, result
            assert len(result['question_diagnostics']) == 1
            diagnostic = result['question_diagnostics'][0]
            assert diagnostic['required'] and diagnostic['needs_recovery'] and diagnostic in result['control_failures']
            assert submissions == []
    asyncio.run(run())


@pytest.mark.parametrize('explicit_plan', [False, True])
def test_optional_malformed_control_preserves_submission_and_explicit_plan_recovery(tmp_path, monkeypatch, explicit_plan):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    from job_applier.browser_controls import observe
    monkeypatch.setattr(fixture, 'FORM_HTML', batch_html().replace('<form>', '<form><input id="unlabelled">'))

    async def run():
        async with fixture.fixture_browser(tmp_path, mode='top') as (page, package, submissions):
            package['attempt'].update(profile_json=batch_profile(), settings_json={'submission_mode': 'submit'})
            ledger = fixture.SubmissionLedger()
            runner = GreenhouseRunner(page, ledger.call, package,
                {'attempt_id': 1, 'worker_id': 'fixture', 'fence': 1},
                {'spool_dir': str(tmp_path / 'spool'), 'cdp_url': page.fixture_endpoint}, page.target_id)
            plans = []
            if explicit_plan:
                observed = await observe(page, package)
                field = next(f for f in observed['inventory'] if f.get('id') == 'unlabelled')
                plans = [{'ref':field['ref'],'question_key':'unreadable-prior-binding',
                          'answer':'synthetic-plan-answer','basis':'explicit_synthetic_answer'}]
            result = await runner.run(30, plans)
            assert result['completed_count'] == 15, result
            if explicit_plan:
                assert result['reason'] == 'control_recovery', result
                assert len(result['control_failures']) == 1
                assert result['control_failures'][0]['explicit_plan']
                assert await page.evaluate('unlabelled.value') == ''
                assert len(runner.read_journal()) == 15 and submissions == []
            else:
                assert result['status'] == 'applied' and result['source'] == 'employer', result
                assert submissions == ['/fake-submit']
    asyncio.run(run())
