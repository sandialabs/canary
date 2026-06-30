# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import shutil
import tempfile
from types import SimpleNamespace

import pytest

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


@pytest.fixture(scope="module")
def setup():
    d = tempfile.mkdtemp()
    try:
        with working_dir(d):
            with open("test.pyt", "w") as fh:
                fh.write(
                    """\
import canary

def test():
    pass

if __name__ == "__main__":
    test()
"""
                )

            run = CanaryCommand("run")
            run(".")

            ns = SimpleNamespace(
                tmp_path=d,
                workspace_path=os.path.join(d, ".canary"),
                results_path=os.path.join(d, "TestResults"),
            )
            yield ns
    finally:
        shutil.rmtree(d)


def test_view_html_report_created_by_run(setup):
    """A normal run should create a view-level HTML report."""
    assert os.path.exists(setup.results_path)

    summary = os.path.join(setup.results_path, "summary.html")
    report = os.path.join(setup.results_path, "_canary", "reports", "html", "index.html")

    assert os.path.exists(report)
    assert os.path.exists(summary)

    if os.path.islink(summary):
        target = os.readlink(summary)
        assert target == os.path.join("_canary", "reports", "html", "index.html")


def test_junit_report(setup):
    report = CanaryCommand("report")
    report("junit", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "junit.xml"))


def test_junit_report_create_compat(setup):
    report = CanaryCommand("report")
    report("junit", "create", "-o", "junit-create.xml", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "junit-create.xml"))


def test_json_report(setup):
    report = CanaryCommand("report")
    report("json", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "canary.json"))


def test_json_report_create_compat(setup):
    report = CanaryCommand("report")
    report("json", "create", "-o", "canary-create.json", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "canary-create.json"))


def test_html_report(setup):
    report = CanaryCommand("report")
    report("html", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "HTML", "index.html"))
    assert os.path.exists(os.path.join(setup.results_path, "HTML", "Total.html"))


def test_html_report_custom_output_dir(setup):
    report = CanaryCommand("report")
    report("html", "-o", "MYHTML", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "MYHTML", "index.html"))
    assert os.path.exists(os.path.join(setup.results_path, "MYHTML", "Total.html"))


def test_markdown_report(setup):
    report = CanaryCommand("report")
    report("markdown", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "MARKDOWN", "index.md"))
    assert os.path.exists(os.path.join(setup.results_path, "MARKDOWN", "Total.md"))


def test_markdown_report_create_compat(setup):
    report = CanaryCommand("report")
    report("markdown", "create", "-o", "MYMARKDOWN", cwd=setup.results_path)

    assert os.path.exists(os.path.join(setup.results_path, "MYMARKDOWN", "index.md"))
    assert os.path.exists(os.path.join(setup.results_path, "MYMARKDOWN", "Total.md"))
