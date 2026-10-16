"""Legacy account creation uses durable, private, per-account random passwords."""
from concurrent.futures import ThreadPoolExecutor
from job_applier.legacy_credentials import account_password


def test_generated_password_is_stable_and_scoped(tmp_path, monkeypatch):
    monkeypatch.delenv('JOB_APPLIER_FALLBACK_PASSWORD', raising=False)
    path = tmp_path/'profile.json'
    profile = {'identity': {'email': 'candidate@example.test'}}
    first = account_password(profile, 'https://jobs.example.test/posting/1', path)
    assert len(first) >= 24
    assert any(c.isupper() for c in first) and any(c.islower() for c in first)
    assert any(c.isdigit() for c in first) and any(not c.isalnum() for c in first)
    assert account_password(profile, 'https://jobs.example.test/posting/2', path) == first
    assert account_password(profile, 'https://other.example.test/job', path) != first
    assert account_password({'identity': {'email': 'other@example.test'}}, 'https://jobs.example.test/job', path) != first
    assert 'accounts' not in profile


def test_explicit_password_precedence_creates_no_store(tmp_path, monkeypatch):
    monkeypatch.setenv('JOB_APPLIER_FALLBACK_PASSWORD', 'synthetic-environment-value')
    path = tmp_path/'profile.json'
    profile = {'accounts': {'default': {'password': 'synthetic-profile-value'}}}
    assert account_password(profile, 'https://example.test/job', path) == 'synthetic-profile-value'
    assert account_password({}, 'https://example.test/job', path) == 'synthetic-environment-value'
    assert not list(tmp_path.iterdir())


def test_concurrent_requests_share_password(tmp_path, monkeypatch):
    monkeypatch.delenv('JOB_APPLIER_FALLBACK_PASSWORD', raising=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: account_password({}, 'https://example.test/job', tmp_path/'profile.json'), range(8)))
    assert len(set(values)) == 1


def test_helpers_reuse_selected_profile_store(tmp_path, monkeypatch):
    monkeypatch.delenv('JOB_APPLIER_FALLBACK_PASSWORD', raising=False)
    profile = {'identity': {'email': 'candidate@example.test'},
               '_legacy_credential_profile_path': str(tmp_path/'selected-profile.json')}
    first = account_password(profile, 'https://example.test/job', tmp_path/'selected-profile.json')
    assert account_password(profile, 'https://example.test/job') == first


def test_no_legacy_caller_retains_shared_fallback_literal():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for name in ['agent.py', 'element_handlers.py', 'platform_handlers/workday.py']:
        tree = ast.parse((root/'job_applier'/name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and len(node.args) > 1:
                first, second = node.args[:2]
                if isinstance(first, ast.Constant) and first.value == 'JOB_APPLIER_FALLBACK_PASSWORD':
                    assert not (isinstance(second, ast.Constant) and second.value), name


def test_workday_resolves_password_only_when_auth_is_used(tmp_path, monkeypatch):
    import asyncio
    from job_applier.platform_handlers.workday import WorkdayHandler, WD_SEL
    monkeypatch.delenv('JOB_APPLIER_FALLBACK_PASSWORD', raising=False)
    profile = {'identity': {'email': 'candidate@example.test'},
               '_legacy_credential_profile_path': str(tmp_path/'profile.json')}
    url = 'https://tenant.myworkdayjobs.com/job/1'
    handler = WorkdayHandler(browser_session=None, profile=profile, job_url=url)
    assert not list(tmp_path.iterdir())
    fills = []
    async def fill(selectors, value):
        fills.append((selectors, value))
        return True, 'synthetic fill'
    async def click(*args, **kwargs):
        return False, 'synthetic submit unavailable'
    handler.el_fill = fill
    handler.el_click = click
    handler.js_click_verified = click
    asyncio.run(handler._auth_action('CREATE_ACCOUNT', {'has_email': True, 'password_count': 2}))
    password = account_password(profile, url)
    assert (WD_SEL['password'], password) in fills
    assert (WD_SEL['verify_password'], password) in fills
