# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import tempfile
from types import SimpleNamespace

import pytest

import canary
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


@pytest.fixture(scope="module")
def setup():
    d = tempfile.mkdtemp()
    with working_dir(d):
        with open("e.pyt", "w") as fh:
            fh.write(
                """\
import canary
canary.directives.parameterize('a', (1, 2, 3, 4, 5, 6, 7, 8))
def test():
    self = canary.get_instance()
    if self.parameters.a == 2:
        raise canary.TestDiffed()
    elif self.parameters.a == 3:
        raise canary.TestFailed()
    elif self.parameters.a == 4:
        raise canary.TestSkipped()
    elif self.parameters.a == 5:
        raise canary.TestTimedOut()
if __name__ == "__main__":
    test()
"""
            )
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import canary
canary.directives.parameterize('a', (1, 2))
def test():
    self = canary.get_instance()
    if self.parameters.a == 2:
        raise canary.TestDiffed()
if __name__ == "__main__":
    test()
"""
            )
        with open("g.pyt", "w") as fh:
            fh.write(
                """\
import canary
canary.directives.generate_composite_base_case()
canary.directives.parameterize('a', (1, 2))
def test(case):
    pass
if __name__ == "__main__":
    self = canary.get_instance()
    if not isinstance(self, canary.TestMultiInstance):
        test(self)
"""
            )
        run = CanaryCommand("run")
        run(".")
        ns = SimpleNamespace(tmp_path=d, results_path=os.path.join(d, "TestResults"))
        yield ns


def test_location_0(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            location = CanaryCommand("location")
            location("-i", "f[a=1]")


def test_location_1(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            location = CanaryCommand("location")
            location("-l", "f[a=1]")


def test_location_2(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            location = CanaryCommand("location")
            location("-s", "f[a=1]")


def test_location_3(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            location = CanaryCommand("location")
            location("-x", "f[a=1]")


def test_location_4(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            location = CanaryCommand("location")
            location("f[a=1]")


def test_log(setup):
    with working_dir(setup.results_path):
        with canary.config.override():
            log = CanaryCommand("log")
            log("f[a=1]")


def test_status(setup):
    with working_dir(setup.results_path), canary.config.override():
        status = CanaryCommand("status")
        status()
        status("-rA")
        status("-rA", "--durations")
        status("--sort-by", "duration")


def test_describe(capsys):
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    describe = CanaryCommand("describe")

    cp = describe(os.path.join(data_dir, "empire.pyt"), debug=True)
    captured = capsys.readouterr()
    assert cp.returncode == 0
    pyt_out = captured.out

    cp = describe(os.path.join(data_dir, "empire.vvt"), debug=True)
    captured = capsys.readouterr()
    assert cp.returncode == 0
    vvt_out = captured.out


def test_find():
    d = os.path.dirname(__file__)
    with working_dir(os.path.join(d, "..")):
        find = CanaryCommand("find")
        find("examples")


def test_config_show():
    config = CanaryCommand("config")
    config("show")


def test_analyze(setup):
    with working_dir(setup.results_path), canary.config.override():
        run = CanaryCommand("run")
        run("-k", "g", "--", "--stage=analyze")


def test_tree():
    examples = os.path.join(os.path.dirname(__file__), "../examples")
    tree = CanaryCommand("tree")
    tree(examples)
