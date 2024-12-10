import os
import subprocess
import sys

import pytest

from _nvtest.util.filesystem import working_dir

this_dir = os.path.dirname(__file__)
examples_dir = os.path.abspath(os.path.join(this_dir, "../src/nvtest/examples"))

if not os.path.exists(examples_dir):
    pytestmark = pytest.mark.skip
if "NVTEST_RUN_EXAMPLES_TEST" not in os.environ:
    pytestmark = pytest.mark.skip


def nvtest(*args):
    argv = [sys.executable, "-m", "nvtest", "-d"]
    argv.extend(args)
    proc = subprocess.run(argv)
    return proc.returncode


def test_basic(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/basic") == 0


def test_analyze_only(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/analyze_only") == 0


def test_centered_space(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/centered_space") == 0


def test_execute_and_analyze(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/execute_and_analyze") == 0


def test_status(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/status") == 30


def test_xstatus(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/xstatus") == 4


def test_parameterize(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/parameterize") == 0


def test_enable(capfd, tmp_path):
    # should get error about not having any tests to run
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/enable") == 7
        capfd.readouterr()
        assert nvtest("run", "-w", "-o", "enable", f"{examples_dir}/enable") == 0
        out, err = capfd.readouterr()
        assert "Initializing test session" in out


def test_timeoutx(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/timeoutx") == 8
        assert nvtest("run", "-w", "-l", "test:timeoutx:5", f"{examples_dir}/timeoutx") == 0


def test_vvt(tmp_path):
    with working_dir(tmp_path):
        assert nvtest("run", "-w", f"{examples_dir}/vvt") == 0
