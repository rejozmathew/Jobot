"""Read-only startup version evidence; never invokes a provider or changes Git."""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def code_evidence():
    version='unknown';dirty=None
    try:
        result=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,timeout=3)
        if result.returncode==0:version=result.stdout.strip()
        result=subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,capture_output=True,text=True,timeout=3)
        if result.returncode==0:dirty=bool(result.stdout.strip())
    except (OSError,subprocess.TimeoutExpired):pass
    skill=ROOT/'skills/productivity/job-apply/SKILL.md'
    skill_hash=hashlib.sha256(skill.read_bytes()).hexdigest() if skill.is_file() else 'unknown'
    digest=hashlib.sha256()
    for path in sorted((ROOT/'job_applier').rglob('*')):
        if path.suffix not in ('.py','.js','.css','.html') or not path.is_file():continue
        digest.update(str(path.relative_to(ROOT)).replace('\\','/').encode());digest.update(path.read_bytes())
    return {'code_version':version,'code_dirty':dirty,'source_fingerprint':digest.hexdigest(),'canonical_skill_hash':skill_hash}
