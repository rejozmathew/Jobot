"""A harness's Python environment must not supply the owned host's dependencies."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from job_applier import workspace_host
from job_applier.workspace_process import process_identity
from test_local_sessions import setup


@pytest.mark.parametrize('contamination', ['path', 'home', 'foreign_interpreter'])
def test_host_uses_repository_dependencies_from_foreign_harness(tmp_path, monkeypatch, contamination):
    service, _, _, workspaces, config = setup(tmp_path)
    config.update(spool_dir=str(tmp_path/'spool'), config_path=str(tmp_path/'runtime.json'))
    (tmp_path/'runtime.json').write_text(json.dumps(config), encoding='utf-8')
    # Emulate a package compiled for the harness's different Python version.
    foreign = tmp_path/'foreign-site-packages'/'pydantic_core'
    foreign.mkdir(parents=True)
    (foreign/'__init__.py').write_text('from ._pydantic_core import PydanticUndefined\n', encoding='utf-8')
    monkeypatch.setenv('PYTHONPATH', str(foreign.parent))
    if contamination == 'home':monkeypatch.setenv('PYTHONHOME', str(tmp_path/'foreign-python-home'))
    if contamination == 'foreign_interpreter':
        monkeypatch.setattr(sys, 'executable', str(tmp_path/'unrelated-harness-python'))
    monkeypatch.setenv('JOBBOT_TEST_DISPLAY', 'preserved')
    smoke = '''import json,os,sys
from job_applier.managed_client import LocalClient
from job_applier.workspace_host import WorkspaceHost
cfg=json.load(open(sys.argv[1]))
with LocalClient(cfg) as client:
    assert client.call('health')['transport']=='local'
assert os.environ['JOBBOT_TEST_DISPLAY']=='preserved'
'''
    launched = []
    def launch(argv, **kwargs):
        # Exercise the actual interpreter/options/environment selected by ensure_host,
        # without launching a browser or leaving a background fixture process.
        index = argv.index('-m')
        completed = subprocess.run(argv[:index]+['-c',smoke,config['config_path']],
            cwd=kwargs['cwd'], capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
        host_id=argv[argv.index('--host-id')+1]
        service.host_registered(workspaces[0]['id'], host_id, process_identity(os.getpid()))
        launched.append(argv)
    monkeypatch.setattr(workspace_host, 'detached_launch', launch)
    result = workspace_host.ensure_host(config, workspaces[0]['id'])
    assert result['host_id'] and len(launched)==1
    assert os.environ['PYTHONPATH']==str(foreign.parent)


def test_existing_host_is_retained_under_foreign_harness(tmp_path, monkeypatch):
    service, _, _, workspaces, config = setup(tmp_path)
    workspace=workspaces[0]
    service.host_registered(workspace['id'], 'existing-host', process_identity(os.getpid()))
    monkeypatch.setenv('PYTHONPATH', str(tmp_path/'foreign-packages'))
    monkeypatch.setattr(workspace_host.FileLock, 'is_locked', lambda path: True)
    monkeypatch.setattr(workspace_host, 'detached_launch', lambda *a,**k: pytest.fail('live host replaced'))
    assert workspace_host.ensure_host(config, workspace['id'])['host_id']=='existing-host'
