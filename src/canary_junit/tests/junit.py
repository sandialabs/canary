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
        _canary.config.resource_pool.populate(cpus=6, gpus=0)
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)


def test_report_junit(tmpdir):
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("run", "-w", os.path.join(root, "examples/basic"))
        run_canary("report", "junit", "create", cwd="TestResults")
        assert os.path.exists("TestResults/junit.xml")


def run_canary(command, *args, cwd=None):
    cmd = [sys.executable, "-m", "canary"]
    if cwd:
        cmd.extend(["-C", cwd])
    cmd.append(command)
    cmd.extend(args)
    subprocess.run(cmd)
