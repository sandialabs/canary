# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.testcase as tc
import canary_vvtest as vvt
from _canary.util.filesystem import working_dir


def test_vvt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.vvt", "w") as fh:
            fh.write(
                """
# VVT: name: baz
# VVT: analyze : --analyze
# VVT: keywords: test unit
# VVT: parameterize (options=baz) : np=1 2 3
# VVT: parameterize : a,b,c=1,11,111 2,22,222 3,33,333
"""
            )
        file = vvt.VVTTestGenerator(".", "test.vvt")
        cases = file.lock(on_options=["baz"])
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
