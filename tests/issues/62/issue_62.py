# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary
from _canary.plugins.builtin.pyt import PYTTestGenerator


def test_issue_62(tmpdir):
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        file = PYTTestGenerator(".", "issue-62.pyt")
        specs = file.lock(on_options=[])
        assert len(specs) == 3
        assert len([spec for spec in specs if not spec.mask]) == 2
