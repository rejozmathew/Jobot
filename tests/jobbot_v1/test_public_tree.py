import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('public_tree', ROOT/'scripts/check_public_tree.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_private_data_paths_are_distinguished_from_templates():
    for name in ['profile.json', 'profile.json.bak-20260817', 'nested/profile.json.credentials.db',
                 'artifacts/screenshot.png', 'scratch/probe.py', 't_wd_probe.py', '.env', 'candidate.json']:
        assert module.private_path(name), name
    for name in ['profile.json.template', 'profile.example.json', '.env.example', 'tests/jobbot_v1/test_core.py']:
        assert not module.private_path(name), name


def test_template_leaves_sensitive_answers_unknown():
    template = json.loads((ROOT/'profile.json.template').read_text())
    assert template == json.loads((ROOT/'profile.example.json').read_text())
    assert template['accounts']['default']['password'] == ''
    assert template['work_authorization']['needs_sponsorship'] is None
    assert template['standard_answers']['background_check_consent'] is None
    assert template['eeo_information']['gender'] == ''
    assert template['years_experience'] is None
    assert template['target_roles'] == []
