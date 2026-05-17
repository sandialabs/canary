# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re

import canary
from canary_vvtest import VVTestAdapter


def test_issue_85(tmpdir):
    with canary.filesystem.working_dir(tmpdir):
        with open("test.vvt", "w") as fh:
            fh.write("# VVT: analyze : --analyze\nimport vvtest_util as vvt\nprint(vvt)")
        generator = VVTestAdapter(os.getcwd(), "test.vvt")
        try:
            generator.lock()
        except ValueError as e:
            match = re.search(
                "Generation of composite base job requires at least one parameter", e.args[0]
            )
            assert match is not None
