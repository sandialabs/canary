# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Environment values must not leak secrets or inject commands into batch scripts."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from _canary.util import envtransport


@pytest.mark.parametrize(
    "name,secret",
    [
        ("GITLAB_TOKEN", True),
        ("CI_JOB_TOKEN", True),
        ("AWS_SECRET_ACCESS_KEY", True),
        ("MY_API_KEY", True),
        ("DB_PASSWORD", True),
        ("PATH", False),
        ("HOME", False),
        ("TOKENIZER_THREADS", False),  # "TOKENIZER" is not the TOKEN component
        ("CANARY_LEVEL", False),
    ],
)
def test_is_secret_name(name, secret):
    assert envtransport.is_secret_name(name) is secret


def test_secret_overrides(monkeypatch):
    monkeypatch.setenv("CANARY_SECRET_VARS", "MY_CORP_*")
    monkeypatch.setenv("CANARY_NOT_SECRET_VARS", "GITLAB_TOKEN")
    assert envtransport.is_secret_name("MY_CORP_THING")
    assert not envtransport.is_secret_name("GITLAB_TOKEN")


HOSTILE = {
    "INJECT": 'x"; echo INJECTED; "',
    "DOLLAR": "$(echo INJECTED)",
    "TICK": "`echo INJECTED`",
    "MULTI": "line1\nline2",
    "JSON": '{"a": [1, "b"]}',
    "BACKSLASH": "a\\b",
    "PLAIN": "/usr/bin:/bin",
}


def test_pack_and_restore_roundtrip():
    packed = envtransport.pack_environment({**HOSTILE, "GONE": None})
    assert packed["PLAIN"] == "/usr/bin:/bin"
    assert packed["GONE"] is None
    for name in ("INJECT", "DOLLAR", "TICK", "MULTI", "JSON", "BACKSLASH"):
        assert name not in packed
    env: dict[str, str] = {k: v for k, v in packed.items() if v is not None}
    restored = envtransport.restore_environment(env)
    assert set(restored) == set(HOSTILE) - {"PLAIN"}
    for k, v in HOSTILE.items():
        assert env[k] == v
    assert envtransport.PAYLOAD_VAR not in env


def test_pack_rejects_invalid_names():
    with pytest.raises(ValueError):
        envtransport.pack_environment({"BAD NAME": "x"})


@pytest.mark.skipif(shutil.which("sh") is None, reason="requires sh")
def test_packed_environment_is_inert_in_generated_script(tmp_path):
    """Write the script exactly as hpc-connect backends do and run it."""
    packed = envtransport.pack_environment(HOSTILE)
    script = tmp_path / "job.sh"
    with open(script, "w") as fh:
        fh.write("#!/bin/sh\n")
        for var, val in packed.items():
            fh.write(f'export {var}="{val}"\n')
        fh.write('echo "PAYLOAD=${CANARY_ENV_B64}"\n')
    cp = subprocess.run(["sh", str(script)], capture_output=True, text=True, check=True)
    assert "INJECTED" not in cp.stdout + cp.stderr
    blob = cp.stdout.strip().split("=", 1)[1]
    env = {envtransport.PAYLOAD_VAR: blob}
    envtransport.restore_environment(env)
    assert env["INJECT"] == HOSTILE["INJECT"]


def test_dist_export_all_skips_secrets(monkeypatch):
    from canary_dist.batchexec import HPCConnectDistRunner

    monkeypatch.setenv("GITLAB_TOKEN", "s3cr3t")
    monkeypatch.setenv("SOME_SETTING", "ok")
    exported = dict(HPCConnectDistRunner.filtered_env())
    assert "GITLAB_TOKEN" not in exported
    assert exported["SOME_SETTING"] == "ok"


def test_env_json_is_redacted_and_private(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from _canary.execution.launcher import _write_env_json
    from _canary.execution.testexec import ExecutionSpace

    monkeypatch.setenv("GITLAB_TOKEN", "s3cr3t")
    monkeypatch.setenv("SOME_SETTING", "ok")
    ws = ExecutionSpace(root=tmp_path, path=Path("job"))
    ws.create()
    _write_env_json(SimpleNamespace(workspace=ws, id="a" * 64))  # type: ignore[arg-type]
    f = tmp_path / "job" / "env.json"
    data = json.loads(f.read_text())
    assert data["GITLAB_TOKEN"] == envtransport.REDACTED
    assert data["SOME_SETTING"] == "ok"
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600

    monkeypatch.setenv("CANARY_ENV_JSON", "0")
    f.unlink()
    _write_env_json(SimpleNamespace(workspace=ws, id="a" * 64))  # type: ignore[arg-type]
    assert not f.exists()


def test_html_does_not_embed_files_outside_workspace(tmp_path):
    from _canary.reporters.html import embeddable

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "out.txt").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    (ws / "link.txt").symlink_to(secret)
    assert embeddable(ws / "out.txt", roots=(ws,))
    assert not embeddable(ws / "link.txt", roots=(ws,))
