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
            ns = SimpleNamespace(tmp_path=d, results_path=os.path.join(d, "TestResults"))
            yield ns
    finally:
        shutil.rmtree(d)


def test_junit(setup):
    report = CanaryCommand("report")
    report("junit", "create", cwd=setup.results_path)
    assert os.path.exists(os.path.join(setup.results_path, "junit.xml"))


def test_html(setup):
    report = CanaryCommand("report")
    report("html", "create", cwd=setup.results_path)
    assert os.path.exists(os.path.join(setup.results_path, "canary-report.html"))


def test_json(setup):
    report = CanaryCommand("report")
    report("json", "create", cwd=setup.results_path)
    assert os.path.exists(os.path.join(setup.results_path, "canary.json"))


def test_markdown(setup):
    report = CanaryCommand("report")
    report("markdown", "create", cwd=setup.results_path)
    assert os.path.exists(os.path.join(setup.results_path, "canary-report.md"))
