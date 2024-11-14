import _nvtest.plugins.nvtest_pyt.generator as pyt
import _nvtest.plugins.nvtest_vvt.generator as vvt
import _nvtest.test.case as tc
from _nvtest.util.filesystem import working_dir


def test_pyt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write(
                """
import nvtest
nvtest.directives.name('baz')
nvtest.directives.analyze()
nvtest.directives.owner('me')
nvtest.directives.keywords('test', 'unit')
nvtest.directives.parameterize('np', (1, 2, 3), when="options='baz'")
nvtest.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
"""
            )
        file = pyt.PYTTestFile(".", "test.pyt")
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
        file = vvt.VVTTestFile(".", "test.vvt")
        cases = file.lock(on_options=["baz"])
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
