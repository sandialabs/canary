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
        with open("e.pyt", "w") as fh:
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
        with open("g.pyt", "w") as fh:
            fh.write(
                """\
import nvtest
nvtest.directives.execbase()
nvtest.directives.parameterize('a', (1, 2))
def test():
    self = nvtest.get_instance()
    if self.paramaters.a == 2:
        raise nvtest.TestDiffed()
def analyze_case():
    pass
def analyze_base_case():
    pass
if __name__ == "__main__":
    pattern = nvtest.patterns.ExecuteAndAnalyze(
        exec_fn=test, analyze_fn=analyze_case, base_fn=analyze_base_case
    )
    test()
"""
            )
        run = NVTestCommand("run")
        run(".")
        ns = SimpleNamespace(tmp_path=d, results_path=os.path.join(d, "TestResults"))
        yield ns
        force_remove(d)


def test_report_cdash(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("cdash", "create")


def test_report_html(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("html", "create")


def test_report_json(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("json", "create")


def test_report_markdown(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("markdown", "create")


def test_report_junit(setup):
    with working_dir(setup.results_path):
        report = NVTestCommand("report")
        report("junit", "create")


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


def test_log(setup):
    with working_dir(setup.results_path):
        log = NVTestCommand("log")
        log("f[a=1]")


def test_status(setup):
    with working_dir(setup.results_path):
        status = NVTestCommand("status")
        status()
        status("-rA")
        status("-l")
        status("-rA", "--durations")
        status("--sort-by", "duration")


def test_describe(capsys):
    from _nvtest.main import NVTestCommand

    data_dir = os.path.join(os.path.dirname(__file__), "data")
    describe = NVTestCommand("describe", debug=True)

    describe(os.path.join(data_dir, "empire.pyt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    pyt_out = captured.out

    describe(os.path.join(data_dir, "empire.vvt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    vvt_out = captured.out


def test_find():
    d = os.path.dirname(__file__)
    with working_dir(os.path.join(d, "..")):
        find = NVTestCommand("find")
        find("examples")


def test_config_show():
    config = NVTestCommand("config")
    config("show")


def test_analyze(setup):
    with working_dir(setup.results_path):
        analyze = NVTestCommand("analyze")
        analyze(".")


def test_tree():
    examples = os.path.join(os.path.dirname(__file__), "../examples")
    tree = NVTestCommand("tree")
    tree(examples)
