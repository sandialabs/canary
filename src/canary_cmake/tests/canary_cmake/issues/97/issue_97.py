# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

import pytest

import canary_cmake.ctest as ctg
from _canary.database import WorkspaceDatabase
from _canary.util.filesystem import force_remove
from _canary.util.filesystem import which


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_issue_97(tmpdir):
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    generator = ctg.CTestTestGenerator(file)
    specs = generator.lock()
    for spec in specs:
        print(spec)
        for dep in spec.dependencies:
            print((spec.id[:7], dep.id[:7]))
    db = WorkspaceDatabase(Path(tmpdir.strpath))
    db.put_specs(specs)
    force_remove(os.path.join(os.path.dirname(__file__), "Testing"))
