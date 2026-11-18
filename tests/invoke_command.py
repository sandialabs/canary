# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""canary_invoke_command: the built-in runs the command; a plugin can take over."""

import subprocess
import sys

PLUGIN = """\
import canary

@canary.hookimpl
def canary_invoke_command(command, args, argv):
    if command.name == "info" and "--take-over" in argv:
        print("taken over")
        return 42
    return None

@canary.hookimpl
def canary_addoption(parser):
    parser.add_argument("--take-over", action="store_true")
"""


def _canary(tmp_path, *args):
    env = {"PYTHONPATH": str(tmp_path), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "canary", "-p", "takeover", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )


def test_plugin_implementation_replaces_local_execution(tmp_path):
    (tmp_path / "takeover.py").write_text(PLUGIN)
    assert _canary(tmp_path, "init", ".").returncode == 0
    proc = _canary(tmp_path, "--take-over", "info")
    assert proc.returncode == 42
    assert "taken over" in proc.stdout


def test_returning_none_falls_through_to_the_builtin(tmp_path):
    (tmp_path / "takeover.py").write_text(PLUGIN)
    assert _canary(tmp_path, "init", ".").returncode == 0
    proc = _canary(tmp_path, "info")
    assert proc.returncode == 0
    assert "taken over" not in proc.stdout
    assert "Workspace" in proc.stdout
