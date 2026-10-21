# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Bad configuration must produce a one-line error naming its source, not a traceback."""

import os
import subprocess
import sys

import pytest

from _canary.config.config import ConfigError
from _canary.config.config import read_config_file


def _canary(*args: str, env: dict[str, str] | None = None, cwd=None):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith("CANARY") or k in ("CI", "GITLAB_CI"):
            e.pop(k)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "canary", *args],
        env=e,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize(
    "content,expect",
    [
        ("canary:\n  plugins: foo\n", "should be instance of 'list'"),
        ("canary: [1, 2\n", "Invalid YAML"),
        ("- a\n- b\n", "expected a mapping"),
    ],
)
def test_bad_global_config_file_is_reported_cleanly(tmp_path, content, expect):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(content)
    cp = _canary("--version", env={"CANARY_GLOBAL_CONFIG": str(cfg)}, cwd=tmp_path)
    assert cp.returncode == 2
    out = cp.stdout + cp.stderr
    assert expect in out
    assert str(cfg) in out
    assert "Traceback" not in out
    assert "During handling of the above exception" not in out


@pytest.mark.parametrize("content", ["", "canary:\n", "# just a comment\n"])
def test_empty_config_files_are_accepted(tmp_path, content):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(content)
    assert read_config_file(cfg) is None
    cp = _canary("--version", env={"CANARY_GLOBAL_CONFIG": str(cfg)}, cwd=tmp_path)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_bad_environment_variable_is_reported_cleanly(tmp_path):
    cp = _canary("--version", env={"CANARY_LOG_LEVEL": "verbose"}, cwd=tmp_path)
    assert cp.returncode == 2
    out = cp.stdout + cp.stderr
    assert "CANARY_LOG_LEVEL" in out and "Wrong log level" in out
    assert "Traceback" not in out


def test_bad_dash_f_config_file_is_reported_cleanly(tmp_path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("canary:\n  plugins: foo\n")
    cp = _canary("-f", str(cfg), "status", cwd=tmp_path)
    assert cp.returncode == 2
    assert "should be instance of 'list'" in cp.stdout + cp.stderr
    assert "Traceback" not in cp.stdout + cp.stderr


def test_read_config_file_rejects_non_mapping_canary_section(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("canary: 5\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        read_config_file(cfg)
