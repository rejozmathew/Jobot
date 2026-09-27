"""Recovery instructions delivered to executors; synthetic contexts only."""
from pathlib import Path

import pytest

from job_applier.application_brief import application_brief
from job_applier.simplify_boundary import SimplifyBoundary
from test_dispatch_queue import enqueue, runtime_fixture


def test_dispatch_and_direct_skill_give_concrete_recovery_not_just_persistence(tmp_path):
    service, asset, jobs, _, config = runtime_fixture(tmp_path)
    item = enqueue(service, asset, jobs)['items'][0]
    brief = application_brief(config, service, item)
    skill = (Path(__file__).resolve().parents[2] /
             'skills/productivity/job-apply/SKILL.md').read_text(encoding='utf-8')
    for prompt in (brief, skill):
        text = ' '.join(prompt.split())
        assert 'Do not stop at the first recoverable obstacle' in text
        assert 'choose a different supported action, execute it, verify its effect' in text
        assert 'empty option list' in text and 'committed selection' in text
        assert 'mailbox checks do not replace refresh-and-refill recovery' in text
        assert 'actions actually tried' in text and 'remaining plausible recovery' in text
    assert brief.index('Do not stop at the first recoverable obstacle') < brief.index('## Assigned job')


def test_queued_brief_exposes_durable_question_handoff_before_ats_details(tmp_path):
    service, asset, jobs, _, config = runtime_fixture(tmp_path)
    item = enqueue(service, asset, jobs)['items'][0]
    brief = application_brief(config, service, item)
    handoff = brief.split('## Missing required answers', 1)[1].split('## ATS reminders', 1)[0]
    handoff = ' '.join(handoff.split())
    assert '"method":"request_answers"' in handoff
    assert handoff.index('request_answers') < handoff.index('park_questions')
    for term in ('approved facts', 'saved answers', 'human_input.messaging.available',
                 'actual reply', 'expected_revision', 'reply_evidence', 'pending questions',
                 'empty parameters', 'Needs your answer', 'Save and queue retry'):
        assert term in handoff
    assert 'known answer rejected by a control' in handoff
    assert 'clarify' in handoff and 'workspace' in handoff


def test_queued_brief_states_shared_autofill_order_before_portal_helpers(tmp_path):
    service, asset, jobs, _, config = runtime_fixture(tmp_path)
    item = enqueue(service, asset, jobs)['items'][0]
    brief = application_brief(config, service, item)
    opening = brief.split('## ATS reminders', 1)[0]
    assert 'selected autofill strategy' in opening
    assert opening.index('application entry and authentication') < opening.index('Simplify Autofill')
    assert opening.index('Simplify Autofill') < opening.index('residual helpers')
    assert 'native-only' in opening


@pytest.mark.parametrize('writer', ['idle', 'active', 'unknown'])
def test_helper_handoff_allows_recovery_after_incomplete_submit_without_bypassing_writer(writer):
    boundary = SimplifyBoundary(None)
    result = boundary._result({'status': 'unknown', 'writer_pending': writer != 'idle'},
                              False, writer, 'controls_unavailable')
    instruction = result['instruction']
    assert 'before submission only' not in instruction
    assert 'incomplete Submit' in instruction
    assert 'accepted confirmation' in instruction
    assert 'verify settlement' in instruction
    assert result['native_takeover_authorized'] is (writer == 'idle')
