"""Acceptance tests for managed CLI entrypoint contracts.

Contract under test:
- Sole entrypoint: python run_applier.py managed ...
- Subcommands listed in --help: init, serve, call, preview-new, backup, migrate-copy, fake-worker.
- managed init --db ABS --instance-id fixture: creates a NEW review-only development DB; stdout JSON health id.
- Reject relative db / missing args / existing db with nonzero exit code, preserving files.
- Bypasses old load_dotenv/profile/global DB startup.
- Subprocess env JOB_APPLIER_DB_PATH points at tmp_path sentinel file with arbitrary bytes.
- Subprocess env JOB_APPLIER_PROFILE_PATH points at synthetic sentinel profile.
- CWD different from repo, uses absolute run_applier.py path.
- Asserts both sentinel hashes unchanged.
- managed preview-new --db ABS: JSON allowed status, no writes.
- managed call --config ABS_JSON --operation health: rejects missing config / missing token env /
  missing instance without creating DB or connecting external.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_APPLIER = (REPO_ROOT / "run_applier.py").resolve()
PYTHON = sys.executable

SENTINEL_DB_BYTES = b"SENTINEL_DB_ARBITRARY_BYTES_\x00\xff\xfe\xca\xfe_NEVER_CORRUPT"
SENTINEL_PROFILE_BYTES = b'{"sentinel_profile": true, "email": "sentinel@example.test"}'


@pytest.fixture
def cli_runner(tmp_path):
    """Sets up an isolated subprocess environment with sentinels and non-repo CWD."""
    sentinel_db = (tmp_path / "sentinel_db.bin").resolve()
    sentinel_db.write_bytes(SENTINEL_DB_BYTES)
    initial_db_hash = hashlib.sha256(SENTINEL_DB_BYTES).hexdigest()

    sentinel_profile = (tmp_path / "sentinel_profile.json").resolve()
    sentinel_profile.write_bytes(SENTINEL_PROFILE_BYTES)
    initial_profile_hash = hashlib.sha256(SENTINEL_PROFILE_BYTES).hexdigest()

    work_dir = (tmp_path / "isolated_work_dir").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    def _run(args, extra_env=None, cwd=work_dir):
        env = dict(os.environ)
        env["JOB_APPLIER_DB_PATH"] = str(sentinel_db)
        env["JOB_APPLIER_PROFILE_PATH"] = str(sentinel_profile)
        if extra_env:
            env.update(extra_env)

        cmd = [PYTHON, str(RUN_APPLIER), "managed"] + list(args)
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )

        assert hashlib.sha256(sentinel_db.read_bytes()).hexdigest() == initial_db_hash, (
            "JOB_APPLIER_DB_PATH sentinel was modified during CLI execution"
        )
        assert hashlib.sha256(sentinel_profile.read_bytes()).hexdigest() == initial_profile_hash, (
            "JOB_APPLIER_PROFILE_PATH sentinel was modified during CLI execution"
        )
        return proc

    return _run


def test_managed_help_lists_all_required_subcommands(cli_runner):
    """managed --help must list init/serve/call/preview-new/backup/migrate-copy/fake-worker."""
    proc = cli_runner(["--help"])
    assert proc.returncode == 0, f"managed --help failed with stderr: {proc.stderr}"
    help_text = proc.stdout.lower()
    for subcmd in (
        "init",
        "serve",
        "call",
        "preview-new",
        "backup",
        "migrate-copy",
        "fake-worker",
    ):
        assert subcmd in help_text, (
            f"Subcommand '{subcmd}' missing from managed --help output:\n{proc.stdout}"
        )


def test_managed_init_creates_review_only_development_db(cli_runner, tmp_path):
    """managed init --db ABS --instance-id fixture creates NEW review-only development DB; stdout JSON health id."""
    target_db = (tmp_path / "created_dev.db").resolve()
    assert not target_db.exists()

    proc = cli_runner(["init", "--db", str(target_db), "--instance-id", "fixture"])
    assert proc.returncode == 0, f"managed init failed with stderr: {proc.stderr}"
    assert target_db.is_file(), "managed init did not create target DB file"

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"managed init stdout is not valid JSON: {proc.stdout!r} ({exc})")

    assert data.get("instance_id") == "fixture"
    submission_mode = data.get("submission_mode") or data.get("settings", {}).get("submission_mode")
    assert submission_mode == "review"


def test_managed_init_rejects_relative_db_missing_args_and_existing_db(cli_runner, tmp_path):
    """Relative db/missing args/existing db fail (nonzero), preserve files."""
    # 1. Relative DB path must fail
    proc_rel = cli_runner(["init", "--db", "relative_path.db", "--instance-id", "fixture"])
    assert proc_rel.returncode != 0

    # 2. Missing args must fail
    proc_no_db = cli_runner(["init", "--instance-id", "fixture"])
    assert proc_no_db.returncode != 0

    proc_no_inst = cli_runner(["init", "--db", str((tmp_path / "unused.db").resolve())])
    assert proc_no_inst.returncode != 0

    proc_empty = cli_runner(["init"])
    assert proc_empty.returncode != 0

    # 3. Existing DB must fail and preserve file content
    existing_db = (tmp_path / "already_exists.db").resolve()
    original_content = b"EXISTING_DATABASE_RAW_BYTES_DO_NOT_OVERWRITE"
    existing_db.write_bytes(original_content)
    orig_hash = hashlib.sha256(original_content).hexdigest()

    proc_exist = cli_runner(["init", "--db", str(existing_db), "--instance-id", "fixture"])
    assert proc_exist.returncode != 0
    assert hashlib.sha256(existing_db.read_bytes()).hexdigest() == orig_hash, (
        "Existing file content was overwritten or modified"
    )


def test_managed_preview_new_json_allowed_no_writes(cli_runner, tmp_path):
    """managed preview-new --db ABS returns JSON allowed status with no writes."""
    target_db = (tmp_path / "preview_target.db").resolve()
    assert not target_db.exists()

    proc = cli_runner(["preview-new", "--db", str(target_db)])
    assert proc.returncode == 0, f"managed preview-new failed with stderr: {proc.stderr}"
    assert not target_db.exists(), "managed preview-new wrote to the database path"

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"managed preview-new stdout is not valid JSON: {proc.stdout!r} ({exc})")

    status_str = str(data.get("status", "")).lower()
    assert "allowed" in status_str or data.get("allowed") is True, (
        f"Expected allowed status in preview-new output, got: {data}"
    )


def test_managed_call_health_rejects_missing_config_missing_token_or_instance(cli_runner, tmp_path):
    """managed call --config ABS_JSON --operation health rejects missing config/token env/instance."""
    abs_db = (tmp_path / "call_target.db").resolve()
    assert not abs_db.exists()

    # 1. Missing token env rejection
    config_dict = {
        "db_path": str(abs_db),
        "instance_id": "fixture",
        "base_url": "http://127.0.0.1:1",
        "operator_token_env": "NONEXISTENT_JOBBOT_TOKEN",
    }
    config_file = (tmp_path / "call_config.json").resolve()
    config_file.write_text(json.dumps(config_dict))

    proc_no_token = cli_runner(["call", "--config", str(config_file), "--operation", "health"])
    assert proc_no_token.returncode != 0
    assert not abs_db.exists(), "managed call created DB on missing token env"

    # 2. Missing config file rejection
    missing_config = (tmp_path / "does_not_exist.json").resolve()
    proc_no_file = cli_runner(["call", "--config", str(missing_config), "--operation", "health"])
    assert proc_no_file.returncode != 0
    assert not abs_db.exists()

    # 3. Missing instance rejection (DB does not exist, token provided)
    config_uninit = {
        "db_path": str((tmp_path / "uninitialized.db").resolve()),
        "instance_id": "fixture",
        "base_url": "http://127.0.0.1:1",
        "operator_token_env": "DEFINED_OPERATOR_TOKEN",
    }
    config_file_uninit = (tmp_path / "call_uninit_config.json").resolve()
    config_file_uninit.write_text(json.dumps(config_uninit))

    proc_uninit = cli_runner(
        ["call", "--config", str(config_file_uninit), "--operation", "health"],
        extra_env={"DEFINED_OPERATOR_TOKEN": "synthetic-secret-token"},
    )
    assert proc_uninit.returncode != 0
    assert not Path(config_uninit["db_path"]).exists(), "managed call created DB for uninit instance"
