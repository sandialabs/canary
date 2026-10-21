# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Robustness of rc-file sourcing and environment-module helpers."""

import os
import shutil
import subprocess

import pytest

from _canary.util import module
from _canary.util import shell

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash")


def test_large_output_does_not_deadlock(tmp_path):
    # > 64 KiB on both stdout and stderr used to deadlock (wait() before communicate()).
    rc = tmp_path / "big.sh"
    rc.write_text(
        "export BIG=$(head -c 50000 /dev/zero | tr '\\0' x)\n"
        "i=0; while [ $i -lt 4000 ]; do echo stdout-noise-$i; echo stderr-noise-$i >&2; "
        "i=$((i+1)); done\n"
    )
    env = shell.Bash().source_rcfile(str(rc), timeout=60)
    assert len(env["BIG"]) == 50000


def test_values_are_exact(tmp_path):
    rc = tmp_path / "vals.sh"
    rc.write_text(
        "export Q='he said \"hi\" $HOME'\n"
        "export ML='line1\nline2'\n"
        "export BS='a\\b'\n"
        "export EMPTY=\n"
        "export UNI='ünï'\n"
    )
    env = shell.Bash().source_rcfile(str(rc))
    assert env["Q"] == 'he said "hi" $HOME'
    assert env["ML"] == "line1\nline2"
    assert env["BS"] == "a\\b"
    assert env["EMPTY"] == ""
    assert env["UNI"] == "ünï"
    assert "PWD" not in env and "SHLVL" not in env


def test_failing_rcfile_raises(tmp_path):
    rc = tmp_path / "fail.sh"
    rc.write_text("export X=1\necho oops >&2\nreturn 3 2>/dev/null || exit 3\n")
    with pytest.raises(shell.RcFileError, match="exit code 3"):
        shell.Bash().source_rcfile(str(rc))


def test_rcfile_timeout(tmp_path):
    rc = tmp_path / "slow.sh"
    rc.write_text("sleep 30\n")
    with pytest.raises(shell.RcFileError, match="Timed out"):
        shell.Bash().source_rcfile(str(rc), timeout=0.5)


def test_source_restores_environment_on_error(tmp_path):
    rc = tmp_path / "tok.sh"
    rc.write_text("export CANARY_TEST_TOKEN=secret\n")
    os.environ.pop("CANARY_TEST_TOKEN", None)
    with pytest.raises(RuntimeError):
        with shell.source(str(rc)):
            assert os.environ["CANARY_TEST_TOKEN"] == "secret"
            raise RuntimeError
    assert "CANARY_TEST_TOKEN" not in os.environ


@pytest.fixture
def fake_module(tmp_path, monkeypatch):
    """Install a bash ``module`` function that records loads and is very chatty."""
    script = tmp_path / "module.sh"
    script.write_text(
        "module() {\n"
        '  case "$1" in\n'
        '    load) export LOADED_MODS="${LOADED_MODS:+$LOADED_MODS:}$2";'
        " i=0; while [ $i -lt 5000 ]; do echo chatty-$i; i=$((i+1)); done ;;\n"
        '    show) echo "module-whatis $2";'
        " i=0; while [ $i -lt 5000 ]; do echo help-$i; i=$((i+1)); done ;;\n"
        "    fail) return 1 ;;\n"
        "    *) return 0 ;;\n"
        "  esac\n"
        "}\n"
        "export -f module\n"
    )
    out = subprocess.run(
        ["bash", "-c", f"source {script}; env -0"], capture_output=True, check=True
    ).stdout
    for entry in out.strip(b"\0").split(b"\0"):
        k, _, v = entry.partition(b"=")
        if k.startswith(b"BASH_FUNC_module"):
            monkeypatch.setenv(k.decode(), v.decode())
    monkeypatch.delenv("LOADED_MODS", raising=False)


def test_module_load_is_quoted_and_does_not_deadlock(fake_module):
    module.load("foo/1.0; echo INJECTED")
    # The whole string is a single argument -- nothing after ';' was executed.
    assert os.environ["LOADED_MODS"] == "foo/1.0; echo INJECTED"


def test_module_loaded_restores_modulepath(fake_module, monkeypatch):
    monkeypatch.setenv("MODULEPATH", "/orig")
    with module.loaded("bar", use="/opt/mods"):
        assert os.environ["MODULEPATH"].startswith("/opt/mods:")
        assert os.environ["LOADED_MODS"] == "bar"
    assert os.environ["MODULEPATH"] == "/orig"
    assert "LOADED_MODS" not in os.environ


def test_module_failure_raises(fake_module):
    with pytest.raises(module.ModuleError):
        module._module("purge", environb={})  # empty env: `module` is undefined
