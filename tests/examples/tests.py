import os
import shutil
import subprocess
import sys

this_dir = os.path.dirname(__file__)


def nvtest(*args):
    argv = [sys.executable, "-m", "nvtest", "-d"]
    argv.extend(args)
    proc = subprocess.run(argv)
    return proc.returncode


def test_basic():
    assert nvtest("run", "-w", f"{this_dir}/basic") == 0


def test_analyze_only():
    assert nvtest("run", "-w", f"{this_dir}/analyze_only") == 0


def test_centered_space():
    assert nvtest("run", "-w", f"{this_dir}/centered_space") == 0


def test_execute_and_analyze():
    assert nvtest("run", "-w", f"{this_dir}/execute_and_analyze") == 0


def test_status():
    assert nvtest("run", "-w", f"{this_dir}/status") == 22


def test_xstatus():
    assert nvtest("run", "-w", f"{this_dir}/xstatus") == 4


def test_parameterize():
    assert nvtest("run", "-w", f"{this_dir}/parameterize") == 0


def test_enable(capfd):
    # should get error about not having any tests to run
    assert nvtest("run", "-w", f"{this_dir}/enable") == 7
    capfd.readouterr()
    assert nvtest("run", "-w", "-o", "enable", f"{this_dir}/enable") == 0
    out, err = capfd.readouterr()
    assert "Beginning test session" in out


def teardown():
    if os.path.exists("TestResults"):
        shutil.rmtree("TestResults")
