# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.plugins.generators.pyt as pyt
import _canary.plugins.generators.vvtest as vvt
import _canary.test.case as tc
from _canary.util.filesystem import working_dir


def test_pyt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write(
                """
import canary
canary.directives.name('baz')
canary.directives.analyze()
canary.directives.owner('me')
canary.directives.keywords('test', 'unit')
canary.directives.parameterize('cpus', (1, 2, 3), when="options='baz'")
canary.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
"""
            )
        file = pyt.PYTTestGenerator(".", "test.pyt")
        cases = file.lock(on_options=["baz"])
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)


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
