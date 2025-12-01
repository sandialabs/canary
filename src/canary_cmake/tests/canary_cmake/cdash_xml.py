# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import importlib.resources
import os
import subprocess
import sys

import pytest

import _canary.config
from _canary.util.filesystem import working_dir


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.Config()
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)


def test_report_cdash(tmpdir):
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("init", ".")
        run_canary("add", os.path.join(root, "examples/basic"))
        run_canary("run")
        run_canary("report", "cdash", "create")
        assert os.path.exists("TestResults/CDASH")


def run_canary(command, *args, cwd=None):
    cmd = [sys.executable, "-m", "canary", "-d", "-r", "cpus:6", "-r", "gpus:0"]
    if cwd:
        cmd.extend(["-C", cwd])
    cmd.append(command)
    cmd.extend(args)
    subprocess.run(cmd)
