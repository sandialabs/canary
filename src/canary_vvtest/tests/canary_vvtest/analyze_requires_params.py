# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for VVT analyze directive validation.

Verifies that generating a composite (analyze) spec without any parameterization
raises a descriptive error, since an analyze-only test has nothing to aggregate.
"""

import os
import re

import canary
from canary_vvtest import VVTestSpecGenerator


def test_analyze_without_parameterize_raises(tmpdir):
    """A VVT file with only an analyze directive and no parameterize raises ValueError."""
    with canary.filesystem.working_dir(tmpdir):
        with open("test.vvt", "w") as fh:
            fh.write("# VVT: analyze : --analyze\nimport vvtest_util as vvt\nprint(vvt)")
        generator = VVTestSpecGenerator(os.getcwd(), "test.vvt")
        try:
            generator.lock()
        except ValueError as e:
            match = re.search(
                "Generation of composite base job requires at least one parameter", e.args[0]
            )
            assert match is not None
