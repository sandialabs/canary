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
nvtest.directives.parameterize('a', (1, 2, 3, 4, 5, 6, 7, 8))
def test():
    self = nvtest.get_instance()
    if self.paramaters.a == 2:
        raise nvtest.TestDiffed()
    elif self.paramaters.a == 3:
        raise nvtest.TestFailed()
    elif self.paramaters.a == 4:
        raise nvtest.TestSkipped()
    elif self.paramaters.a == 5:
        raise nvtest.TestTimedOut()
if __name__ == "__main__":
    test()
"""
            )
        run = NVTestCommand("run")
        run(".")
        ns = SimpleNamespace(tmp_path=d, results_path=os.path.join(d, "TestResults"))
        yield ns
        force_remove(d)


def test_cdash(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("cdash", "create")


def test_html(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("html", "create")


def test_json(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("json", "create")


def test_markdown(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("markdown", "create")


def test_junit(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("junit", "create")
