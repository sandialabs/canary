# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from types import SimpleNamespace

import pytest

import canary
from _canary.plugins.subcommands.config import show_config
from _canary.plugins.subcommands.describe import Describe
from _canary.plugins.subcommands.find import Find
from _canary.plugins.subcommands.location import Location
from _canary.plugins.subcommands.log import Log
from _canary.plugins.subcommands.status import Status
from _canary.plugins.subcommands.tree import Tree
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand
from _canary.workspace import Workspace


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    d = tmp_path_factory.mktemp("canary-command")

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
def test(job):
    pass
if __name__ == "__main__":
    self = canary.get_instance()
    if not isinstance(self, canary.TestMultiInstance):
        test(self)
"""
            )

        with canary.config.override():
            workspace = Workspace.create(d)
            specs = workspace.collect({str(d): []})
            session = workspace.run(specs, only="all")

        jobs = workspace.load_jobs()
        f_a1_job = next(job for job in jobs if job.name == "f.a=1")

        ns = SimpleNamespace(
            tmp_path=d,
            workspace=workspace,
            session=session,
            results_path=d / "TestResults",
            f_a1_id=f_a1_job.id,
        )
        yield ns


def run_location(testspec: str, *, input=False, log=False, source=False, x=False) -> int:
    args = argparse.Namespace(
        show_input=input,
        show_log=log,
        show_source_dir=source,
        show_working_directory=x,
        testspec=testspec,
    )
    return Location().execute(args)


def run_status(*, report_chars="dftns", durations=None, sort_by="name") -> int:
    args = argparse.Namespace(
        durations=durations,
        format_cols="ID,Name,Session,Exit Code,Duration,Status,Details",
        report_chars=report_chars,
        sort_by=sort_by,
        specs=[],
    )
    return Status().execute(args)


def test_location_0(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, input=True) == 0


def test_location_1(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, log=True) == 0


def test_location_2(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, source=True) == 0


def test_location_3(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, x=True) == 0


def test_location_4(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id) == 0


def test_log(setup, monkeypatch):
    from _canary.plugins.subcommands import log as log_module

    monkeypatch.setattr(log_module, "page_text", lambda text: None)

    with working_dir(setup.results_path), canary.config.override():
        args = argparse.Namespace(error=False, raw=False, testspec=setup.f_a1_id)
        assert Log().execute(args) == 0


def test_status(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_status() == 0
        assert run_status(report_chars="A") == 0
        assert run_status(report_chars="A", durations=10) == 0
        assert run_status(sort_by="duration") == 0


def test_describe(capsys):
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    with canary.config.override():
        args = argparse.Namespace(on_options=None, testspec=os.path.join(data_dir, "empire.pyt"))
        rc = Describe().execute(args)
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out

        args = argparse.Namespace(on_options=None, testspec=os.path.join(data_dir, "empire.vvt"))
        rc = Describe().execute(args)
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out


def test_find():
    d = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(d, ".."))
    examples = os.path.join(root, "examples")

    with working_dir(root), canary.config.override():
        args = argparse.Namespace(
            scanpaths={examples: []},
            on_options=None,
            keyword_exprs=None,
            parameter_expr=None,
            owners=None,
            regex_filter=None,
            print_paths=False,
            print_files=False,
            print_graph=False,
            print_lock=False,
            print_keywords=False,
        )
        assert Find().execute(args) == 0


def test_config_show():
    args = argparse.Namespace(file_paths=False, format="yaml", section=None)
    assert show_config(args) == 0


def test_analyze(setup):
    # Keep this one as a real command invocation because it specifically
    # tests command-line script-argument behavior after "--".
    #
    # Use --only all because the setup run already produced successful
    # results for the g jobs; the default --only not_pass would exclude them.
    with working_dir(setup.results_path), canary.config.override():
        run = CanaryCommand("run")
        cp = run("--only", "all", "-k", "g", "--", "--stage=analyze")
        assert cp.returncode == 0


def test_tree():
    examples = os.path.join(os.path.dirname(__file__), "../examples")

    args = argparse.Namespace(a=False, d=False, exclude_results=False, directory=examples)
    assert Tree().execute(args) == 0
