# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys

import pytest

from _canary.util.filesystem import working_dir

this_dir = os.path.dirname(__file__)
examples_dir = os.path.abspath(os.path.join(this_dir, "../src/canary/examples"))

if not os.path.exists(examples_dir):
    pytestmark = pytest.mark.skip
if "CANARY_RUN_EXAMPLES_TEST" not in os.environ:
    pytestmark = pytest.mark.skip


def canary(*args):
    argv = [sys.executable, "-m", "canary", "-d"]
    argv.extend(args)
    proc = subprocess.run(argv)
    return proc.returncode


def test_enable(capfd, tmp_path):
    # should get error about not having any tests to run
    with working_dir(tmp_path):
        assert canary("run", "-w", f"{examples_dir}/enable") == 7
        capfd.readouterr()
        assert canary("run", "-w", "-o", "enable", f"{examples_dir}/enable") == 0
        out, err = capfd.readouterr()
        assert "Initializing test session" in out


def test_timeoutx(tmp_path):
    with working_dir(tmp_path):
        assert canary("run", "-w", f"{examples_dir}/timeoutx") == 8
        assert canary("run", "-w", "--timeout-multiplier=5", f"{examples_dir}/timeoutx") == 0


@pytest.mark.parametrize(
    "subdir,exitcode",
    [
        ("random_space", 0),
        ("basic", 0),
        ("status", 30),
        ("vvt", 0),
        ("centered_space", 0),
        ("depends_on", 4),
        ("parameterize", 0),
        ("rebaseline", 0),
        ("xstatus", 4),
        ("execute_and_analyze", 0),
        ("centered_space", 0),
        ("analyze_only", 0),
    ],
)
def test_subdir(tmp_path, subdir, exitcode):
    with working_dir(tmp_path):
        assert canary("run", "-w", f"{examples_dir}/{subdir}") == exitcode
