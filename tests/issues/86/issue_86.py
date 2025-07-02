# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

import _canary.plugins.builtin.ctest as ctg
from _canary.util.filesystem import force_remove
from _canary.util.filesystem import which


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_issue_86():
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    generator = ctg.CTestTestGenerator(file)
    cases = generator.lock()
    for case in cases:
        assert os.path.basename(case.command()[0]) == "echo"
        assert case.command()[-1] == "yaml"
    force_remove(os.path.join(os.path.dirname(__file__), "Testing"))
