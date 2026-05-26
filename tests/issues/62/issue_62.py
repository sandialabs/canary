# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
import canary_pyt.pyt as pyt


def test_issue_62(tmpdir):
    # Keep original working-dir behavior: issue-62.pyt is located alongside this test file
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        m = pyt.PYTModel(".", "issue-62.pyt")
        calls = pyt.PYTLoader(file=m.file).parse()
        pyt.PYTAdapter(m).apply(calls)

        specs = pyt.PYTLockEmitter().lock(m, on_options=[])
        assert len(specs) == 3
        assert len([spec for spec in specs if not spec.mask]) == 2
