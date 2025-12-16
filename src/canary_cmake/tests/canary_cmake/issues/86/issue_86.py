# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

import canary_cmake.ctest as ctg
from _canary.util.filesystem import force_remove
from _canary.util.filesystem import which


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_issue_86():
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    generator = ctg.CTestTestGenerator(file)
    specs = generator.lock()
    for spec in specs:
        assert os.path.basename(spec.attributes["command"][0]) == "echo"
        assert spec.attributes["command"][-1] == "yaml"
    force_remove(os.path.join(os.path.dirname(__file__), "Testing"))
