"""Acceptance and contract tests for staged skill specifications and references.

Verifies:
- Staged skill paths:
  1) skills/productivity/job-apply/SKILL.md + references/{simplify,workday,greenhouse,cdp-recipes,accounts-and-mail}.md
  2) skills/productivity/job-application-submit/SKILL.md (deprecated trigger)
  3) skills/job-posting-harvest/SKILL.md + references/{ats-map-2026-08,discovery-and-handoff}.md + scripts/{ats_probe,intake_results}.py
- Frontmatter specification:
  - name non-empty string
  - description non-empty string, length <= 60 characters, ends with a period '.'
  - human-first author specified in frontmatter
  - non-empty markdown body
- Relative markdown link validation:
  - All relative links resolve to existing files
- Safety invariants across all documents:
  - No personal absolute paths (e.g. C:\\Users\\rejoz, /home/rejoz)
  - No personal email or phone examples (only synthetic documentation domains/placeholders)
  - No kill-all-browser commands (killall, taskkill, pkill on whole browser)
  - No force-submit instructions (bypass review, blind submit)
  - No blanket factual answer instructions (always answer yes, blanket yes)
- Canonical job-apply skill semantics:
  - Names jobbot accept, jobbot next, jobbot checkpoint, jobbot finish
  - Names app-owned controls
  - Names selected profile facts
  - Names account namespace+identity
  - Names Simplify preferred + bounded flexible recovery
  - Names actual evidence
  - States no redundant full final audit
- Deprecated trigger skill semantics:
  - Deprecated trigger notice, points to job-apply, not a second normal execution recipe
- Harvest skill and references semantics:
  - Preserves Greenhouse public API
  - Preserves same-origin Workday CXS
  - Preserves known WAF/login/DNS failures
  - Preserves dated map disclaimer
  - Preserves verdict set
  - Preserves dynamic exclusions
  - Preserves every recovered-role accounting
  - Preserves shared app intake with no auto-apply

Missing staged files/modules are expected RED during test-only stage (Primary authors staged copies).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

STAGED_SKILLS: dict[str, dict[str, Any]] = {
    "job-apply": {
        "dir": REPO_ROOT / "skills" / "productivity" / "job-apply",
        "skill": REPO_ROOT / "skills" / "productivity" / "job-apply" / "SKILL.md",
        "references": [
            "simplify.md",
            "workday.md",
            "greenhouse.md",
            "cdp-recipes.md",
            "accounts-and-mail.md",
        ],
        "scripts": [],
    },
    "job-application-submit": {
        "dir": REPO_ROOT / "skills" / "productivity" / "job-application-submit",
        "skill": REPO_ROOT / "skills" / "productivity" / "job-application-submit" / "SKILL.md",
        "references": [],
        "scripts": [],
    },
    "job-posting-harvest": {
        "dir": REPO_ROOT / "skills" / "job-posting-harvest",
        "skill": REPO_ROOT / "skills" / "job-posting-harvest" / "SKILL.md",
        "references": [
            "ats-map-2026-08.md",
            "discovery-and-handoff.md",
        ],
        "scripts": [
            "ats_probe.py",
            "intake_results.py",
        ],
    },
}

ALL_STAGED_PATHS: list[Path] = []
for _info in STAGED_SKILLS.values():
    ALL_STAGED_PATHS.append(_info["skill"])
    for _ref in _info["references"]:
        ALL_STAGED_PATHS.append(_info["dir"] / "references" / _ref)
    for _scr in _info["scripts"]:
        ALL_STAGED_PATHS.append(_info["dir"] / "scripts" / _scr)

ALL_STAGED_DOCS: list[Path] = [p for p in ALL_STAGED_PATHS if p.suffix == ".md"]


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter enclosed by leading and terminating '---'."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm_text = "\n".join(lines[1:idx])
            body = "\n".join(lines[idx + 1 :]).strip()
            try:
                data = yaml.safe_load(fm_text) or {}
            except Exception:
                data = {}
            return data, body
    return {}, content


# ---------------------------------------------------------------------------
# Staged File Existence Contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_key", list(STAGED_SKILLS.keys()))
def test_staged_skill_files_exist(skill_key: str) -> None:
    """Verify all staged skills, references, and scripts exist under skills/."""
    spec = STAGED_SKILLS[skill_key]
    skill_file = spec["skill"]
    assert skill_file.is_file(), (
        f"Missing staged skill file: {skill_file.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    for ref_name in spec["references"]:
        ref_file = spec["dir"] / "references" / ref_name
        assert ref_file.is_file(), (
            f"Missing staged reference: {ref_file.relative_to(REPO_ROOT)} "
            "(expected RED in test-only stage; Primary owns authoring staged copies)"
        )

    for scr_name in spec["scripts"]:
        scr_file = spec["dir"] / "scripts" / scr_name
        assert scr_file.is_file(), (
            f"Missing staged script: {scr_file.relative_to(REPO_ROOT)} "
            "(expected RED in test-only stage; Primary owns authoring staged copies)"
        )


# ---------------------------------------------------------------------------
# Frontmatter Contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_key", list(STAGED_SKILLS.keys()))
def test_skill_frontmatter_contracts(skill_key: str) -> None:
    """SKILL.md frontmatter must contain name, <=60 char description ending with '.', and human-first author."""
    skill_file = STAGED_SKILLS[skill_key]["skill"]
    assert skill_file.is_file(), (
        f"Missing staged skill file: {skill_file.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = skill_file.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    assert fm, f"Frontmatter missing or unparseable in {skill_file.relative_to(REPO_ROOT)}"

    # 1. Name
    name = fm.get("name")
    assert isinstance(name, str) and name.strip(), f"Frontmatter 'name' must be a non-empty string in {skill_key}"
    assert name == skill_key or name.replace("-", "_") == skill_key.replace("-", "_"), (
        f"Skill name '{name}' does not match expected skill key '{skill_key}'"
    )

    # 2. Description: <= 60 chars, ends with a period
    desc = fm.get("description")
    assert isinstance(desc, str) and desc.strip(), f"Frontmatter 'description' missing or empty in {skill_key}"
    assert len(desc) <= 60, (
        f"Frontmatter 'description' exceeds 60 characters ({len(desc)} chars): '{desc}' in {skill_key}"
    )
    assert desc.endswith("."), f"Frontmatter 'description' must end with a period ('.'), got '{desc}' in {skill_key}"

    # 3. Human-first author
    author = fm.get("author") or fm.get("author_type")
    human_flag = fm.get("human_first")
    is_human = (author and any(h in str(author).lower() for h in ("human", "human-first", "human_first"))) or (
        human_flag is True
    )
    assert is_human, (
        f"Frontmatter must declare a human-first author (e.g. 'author: human' or 'author: human-first'), "
        f"got author={author!r}, human_first={human_flag!r} in {skill_key}"
    )

    # 4. Nonempty body
    assert body.strip(), f"SKILL.md body is empty in {skill_file.relative_to(REPO_ROOT)}"


# ---------------------------------------------------------------------------
# Relative Linked References
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_path", ALL_STAGED_DOCS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_markdown_relative_links_resolve(doc_path: Path) -> None:
    """All relative markdown links [text](path) in staged docs must resolve to existing files."""
    assert doc_path.is_file(), (
        f"Staged doc missing: {doc_path.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = doc_path.read_text(encoding="utf-8")
    # Match markdown links [label](target)
    link_matches = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

    for label, target in link_matches:
        target = target.strip()
        # Skip external URLs, anchor-only links, mailto
        if (
            target.startswith(("http://", "https://", "mailto:", "ftp://"))
            or target.startswith("#")
            or not target
        ):
            continue

        # Strip internal anchor from target
        rel_target = target.split("#", 1)[0].strip()
        if not rel_target:
            continue

        resolved = (doc_path.parent / rel_target).resolve()
        assert resolved.exists(), (
            f"Broken relative markdown link in {doc_path.relative_to(REPO_ROOT)}: "
            f"[{label}]({target}) resolves to missing path {resolved}"
        )


# ---------------------------------------------------------------------------
# Safety Invariants across All Staged Markdown Documents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_path", ALL_STAGED_DOCS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_safety_no_personal_paths_emails_or_phones(doc_path: Path) -> None:
    """No personal absolute paths, real emails, or real phone examples allowed in staged docs."""
    assert doc_path.is_file(), (
        f"Staged doc missing: {doc_path.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = doc_path.read_text(encoding="utf-8")

    # 1. No personal absolute paths
    personal_path_match = re.search(
        r"([A-Za-z]:[\\/][Uu]sers[\\/]rejoz|/home/rejoz|/Users/rejoz|rejoz[\\/])",
        content,
        re.IGNORECASE,
    )
    assert not personal_path_match, (
        f"Personal path detected in {doc_path.relative_to(REPO_ROOT)}: '{personal_path_match.group(0)}'"
    )

    # 2. No personal emails (only synthetic documentation domains/placeholders allowed)
    allowed_domains = {"example.com", "example.test", "example.org", "company.test", "acme.test", "employer.test"}
    email_pattern = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
    for full_match, username, domain in email_pattern.findall(content):
        # Allow placeholder formats like user@example.test or <email>
        assert domain.lower() in allowed_domains or "example" in domain.lower(), (
            f"Disallowed personal/non-synthetic email in {doc_path.relative_to(REPO_ROOT)}: '{full_match}'"
        )

    # 3. No real phone numbers (must be 555 dummy or template placeholder)
    phone_pattern = re.compile(r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]([0-9]{3})[-.]([0-9]{4})\b")
    for full_match, area, prefix, line in phone_pattern.findall(content):
        assert prefix == "555" or area == "555", (
            f"Disallowed non-dummy phone number in {doc_path.relative_to(REPO_ROOT)}: '{full_match}'"
        )


@pytest.mark.parametrize("doc_path", ALL_STAGED_DOCS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_safety_no_kill_all_browser_force_submit_or_blanket_answers(doc_path: Path) -> None:
    """No kill-all-browser commands, force-submit recipes, or blanket factual screening answers."""
    assert doc_path.is_file(), (
        f"Staged doc missing: {doc_path.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = doc_path.read_text(encoding="utf-8")

    # 1. No kill-all-browser recipes
    kill_all_match = re.search(
        r"(killall\s+(?:chrome|brave|firefox)|pkill\s+(?:-f\s+)?(?:chrome|brave|firefox)|"
        r"taskkill\s+[^\n]*(?:chrome|brave)\.exe|kill[- ]all[- ]browser|terminate\s+all\s+browser)",
        content,
        re.IGNORECASE,
    )
    assert not kill_all_match, (
        f"Disallowed kill-all-browser recipe in {doc_path.relative_to(REPO_ROOT)}: '{kill_all_match.group(0)}'"
    )

    # 2. No force-submit recipes
    force_submit_match = re.search(
        r"(force[- ]submit|bypass[- ]review|blind(?:ly)?[- ]submit|submit[- ]without[- ]review|"
        r"force_submit|ignore\s+review\s+state)",
        content,
        re.IGNORECASE,
    )
    assert not force_submit_match, (
        f"Disallowed force-submit instruction in {doc_path.relative_to(REPO_ROOT)}: '{force_submit_match.group(0)}'"
    )

    # 3. No blanket factual answer instructions
    blanket_match = re.search(
        r"(always\s+(?:answer|select|choose|default\s+to)\s+yes|blanket\s+yes|"
        r"answer\s+yes\s+to\s+all|blanket\s+factual\s+answers?)",
        content,
        re.IGNORECASE,
    )
    assert not blanket_match, (
        f"Disallowed blanket factual answer instruction in {doc_path.relative_to(REPO_ROOT)}: '{blanket_match.group(0)}'"
    )


# ---------------------------------------------------------------------------
# Canonical Job-Apply Skill Semantic Contract
# ---------------------------------------------------------------------------


def test_canonical_job_apply_skill_semantic_contract() -> None:
    """skills/productivity/job-apply/SKILL.md must name protocol operations and core concepts."""
    skill_file = STAGED_SKILLS["job-apply"]["skill"]
    assert skill_file.is_file(), (
        f"Missing staged canonical skill: {skill_file.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = skill_file.read_text(encoding="utf-8")

    # 1. Exact known API labels
    # Local startup supersedes legacy accept/claim/checkpoint choreography.
    assert re.search(r"\bjobbot\s+start\b", content, re.IGNORECASE), "Must name 'jobbot start'"
    assert re.search(r"\bjobbot\s+pause\b", content, re.IGNORECASE), "Must name 'jobbot pause'"
    assert re.search(r"\bjobbot\s+stop\b", content, re.IGNORECASE), "Must name 'jobbot stop'"
    assert re.search(r"\bjobbot\s+finish\b", content, re.IGNORECASE), "Must name 'jobbot finish'"

    # 2. Core conceptual requirements (semantic matching)
    assert re.search(r"app[- ]owned\s+controls?", content, re.IGNORECASE), "Must mention app-owned controls"
    assert re.search(r"(?:selected\s+profile(?:\s+facts)?|profile\s+facts)", content, re.IGNORECASE), (
        "Must mention selected profile facts"
    )
    assert re.search(r"namespace", content, re.IGNORECASE) and re.search(r"identity", content, re.IGNORECASE), (
        "Must mention account namespace and identity"
    )
    assert re.search(r"simplify", content, re.IGNORECASE) and re.search(r"prefer(?:red)?", content, re.IGNORECASE), (
        "Must mention Simplify preferred"
    )
    assert re.search(r"bounded.*(?:recovery|fallback)", content, re.IGNORECASE), (
        "Must mention bounded flexible recovery"
    )
    assert re.search(r"(?:actual\s+evidence|page\s+evidence|dom\s+evidence)", content, re.IGNORECASE), (
        "Must mention actual evidence"
    )
    assert re.search(
        r"(?:no\s+redundant.*(?:final\s+audit|full\s+audit)|avoid\s+redundant.*(?:final\s+audit|full\s+audit)|without\s+(?:a\s+)?redundant\s+full\s+final\s+audit)",
        content,
        re.IGNORECASE,
    ), "Must specify no redundant full final audit"


# ---------------------------------------------------------------------------
# Deprecated Trigger Skill Contract
# ---------------------------------------------------------------------------


def test_deprecated_trigger_skill_contract() -> None:
    """skills/productivity/job-application-submit/SKILL.md must be a deprecated trigger, not normal recipe."""
    skill_file = STAGED_SKILLS["job-application-submit"]["skill"]
    assert skill_file.is_file(), (
        f"Missing staged deprecated skill: {skill_file.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )

    content = skill_file.read_text(encoding="utf-8")
    assert re.search(r"\b(?:deprecated|deprecation)\b", content, re.IGNORECASE), (
        "Skill must explicitly state it is deprecated"
    )
    assert re.search(r"job-apply", content, re.IGNORECASE), (
        "Deprecated trigger must direct users/agents to canonical 'job-apply' skill"
    )
    assert not re.search(r"normal\s+execution\s+recipe", content, re.IGNORECASE), (
        "Must not present itself as a normal execution recipe"
    )


# ---------------------------------------------------------------------------
# Harvest Skill and References Semantic Contract
# ---------------------------------------------------------------------------


def test_harvest_skill_and_references_contract() -> None:
    """skills/job-posting-harvest/SKILL.md + references must satisfy harvest invariants."""
    harvest_spec = STAGED_SKILLS["job-posting-harvest"]
    skill_file = harvest_spec["skill"]
    ats_map_file = harvest_spec["dir"] / "references" / "ats-map-2026-08.md"
    discovery_file = harvest_spec["dir"] / "references" / "discovery-and-handoff.md"

    for path in (skill_file, ats_map_file, discovery_file):
        assert path.is_file(), (
            f"Missing staged harvest file: {path.relative_to(REPO_ROOT)} "
            "(expected RED in test-only stage; Primary owns authoring staged copies)"
        )

    skill_text = skill_file.read_text(encoding="utf-8")
    ats_map_text = ats_map_file.read_text(encoding="utf-8")
    discovery_text = discovery_file.read_text(encoding="utf-8")
    combined_text = f"{skill_text}\n{ats_map_text}\n{discovery_text}"

    # 1. Greenhouse public API
    assert re.search(
        r"greenhouse.*(?:public\s+api|boards-api\.greenhouse\.io|api)",
        combined_text,
        re.IGNORECASE,
    ), "Must preserve Greenhouse public API"

    # 2. Same-origin Workday CXS
    assert re.search(
        r"(?:workday.*cxs|same[- ]origin.*workday|cxs.*workday)",
        combined_text,
        re.IGNORECASE,
    ), "Must preserve same-origin Workday CXS"

    # 3. Known WAF/login/DNS failures
    assert re.search(r"(?:waf|cloudflare|datadome|challenge)", combined_text, re.IGNORECASE), (
        "Must account for WAF/challenge failures"
    )
    assert re.search(r"(?:login|sign[- ]in).*barrier|login.*wall|auth.*required", combined_text, re.IGNORECASE), (
        "Must account for login barriers"
    )
    assert re.search(r"dns.*(?:fail|resolution|lookup|error)", combined_text, re.IGNORECASE), (
        "Must account for DNS resolution failures"
    )

    # 4. Dated map disclaimer
    assert re.search(
        r"(?:dated|disclaimer|as of 2026-08|snapshot|point[- ]in[- ]time)",
        ats_map_text,
        re.IGNORECASE,
    ), "ats-map-2026-08.md must contain a dated map disclaimer"

    # 5. Verdict set
    assert re.search(r"verdict", combined_text, re.IGNORECASE), "Must define/reference a verdict set"

    # 6. Dynamic exclusions
    assert re.search(
        r"(?:dynamic\s+exclusions?|exclusion\s+patterns?|exclude\s+patterns?)",
        combined_text,
        re.IGNORECASE,
    ), "Must preserve dynamic exclusions"

    # 7. Every recovered-role accounting
    assert re.search(
        r"(?:recovered[- ]role|recovered\s+roles?|every\s+(?:role|posting)|accounting)",
        combined_text,
        re.IGNORECASE,
    ), "Must account for every recovered role"

    # 8. Shared app intake with no auto-apply
    assert re.search(r"intake", combined_text, re.IGNORECASE), "Must specify shared app intake"
    assert re.search(r"no(?:\s+auto[- ]apply|\s+automatic\s+appl)", combined_text, re.IGNORECASE), (
        "Must explicitly specify NO auto-apply during harvest handoff"
    )
