import os
import tempfile
from types import SimpleNamespace

import pytest

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import working_dir


@pytest.fixture(scope="module")
def setup():
    d = tempfile.mkdtemp()
    with working_dir(d):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import nvtest
nvtest.directives.parameterize('a', (1, 2))
def test():
    self = nvtest.get_instance()
    if self.paramaters.a == 2:
        raise nvtest.TestDiffed()
if __name__ == "__main__":
    test()
"""
            )
        run = NVTestCommand("run")
        run(".")
        ns = SimpleNamespace(tmp_path=d, results_path=os.path.join(d, "TestResults"))
        yield ns
        force_remove(d)


def test_location_0(setup):
    with working_dir(setup.results_path):
        location = NVTestCommand("location")
        location("-i", "f[a=1]")


def test_location_1(setup):
    with working_dir(setup.results_path):
        location = NVTestCommand("location")
        location("-l", "f[a=1]")


def test_location_2(setup):
    with working_dir(setup.results_path):
        location = NVTestCommand("location")
        location("-s", "f[a=1]")


def test_location_3(setup):
    with working_dir(setup.results_path):
        location = NVTestCommand("location")
        location("-x", "f[a=1]")


def test_location_4(setup):
    with working_dir(setup.results_path):
        location = NVTestCommand("location")
        location("f[a=1]")
