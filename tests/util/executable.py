# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import pytest

from _canary.util.executable import Executable
from _canary.util.executable import ProcessError


def test_find_prefers_path_over_cwd_shadow(tmp_path, monkeypatch):
    cwd_tool = tmp_path / "git"
    cwd_tool.write_text("#!/bin/sh\nexit 0\n")
    cwd_tool.chmod(0o755)
    monkeypatch.chdir(tmp_path)

    located = Executable.find("git")

    assert located != cwd_tool.resolve()


def test_call_does_not_mutate_caller_env(tmp_path):
    env = {"A": "1"}
    exe = Executable(sys.executable)
    exe.add_default_env(B="2")

    result = exe("-c", "import os; print(os.environ['B'])", output=str, env=env)

    assert result.returncode == 0
    assert result.out is not None and result.out.strip() == "2"
    assert env == {"A": "1"}


def test_process_error_preserves_real_returncode():
    exe = Executable(sys.executable)

    with pytest.raises(ProcessError, match="status 7"):
        exe("-c", "import sys; sys.exit(7)")

    assert exe.returncode == 7


@pytest.mark.skipif(sys.platform == "win32", reason="requires process groups")
def test_timeout_kills_process_group(tmp_path):
    marker = tmp_path / "alive"
    cmd = (
        "import pathlib, subprocess, sys, time; "
        f"pathlib.Path({str(marker)!r}).write_text('x'); "
        f"subprocess.Popen(['sh','-c','rm -f {str(marker)}; sleep 30'], start_new_session=False); "
        "time.sleep(30)"
    )
    exe = Executable(sys.executable)

    with pytest.raises(TimeoutError):
        exe("-c", cmd, timeout=0.5)

    assert not marker.exists()
