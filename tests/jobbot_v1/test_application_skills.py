"""Repository instructions remain portable, discoverable and linked."""
from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[2]


def test_portable_skills_and_thin_entry_frontmatter_and_references():
    paths=[ROOT/'skills/productivity/job-apply/SKILL.md',ROOT/'skills/productivity/workday-simplify/SKILL.md',ROOT/'integrations/hermes_jobbot/skills/job-apply/SKILL.md']
    for path in paths:
        content=path.read_text(encoding='utf-8-sig')
        assert content.startswith('---\n')
        front,body=content[4:].split('\n---\n',1)
        meta=yaml.safe_load(front)
        assert len(meta['description'])<=60 and meta['description'].endswith('.')
        assert meta['name'] and meta['platforms'] and meta['author']
        assert 'C:/Users/' not in content and 'C:/GitClone/' not in content
        for link in re.findall(r'\]\(([^)]+\.md)\)',body):
            assert (path.parent/link).resolve().is_file(),(path,link)
    shim=paths[-1].read_text()
    assert len(shim)<2500 and 'skills/productivity/job-apply/SKILL.md' in shim
    assert 'workday_fast' in paths[1].read_text()
    assert 'all ATS platforms' in paths[0].read_text()


def test_helper_map_and_agent_entry_are_present():
    content=(ROOT/'docs/jobbot-v1/APPLICATION_RUNTIME.md').read_text()
    for name in ('workday_fast.py','application_runtime.py','simplify_observe.js','managed_credentials.py','legacy_history_paths'):
        assert name in content
    assert (ROOT/'docs/jobbot-v1/WORKDAY_NEXT_RUN.md').is_file()
    assert 'workday-simplify/SKILL.md' in (ROOT/'AGENTS.md').read_text()
