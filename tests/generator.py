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
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            on_options=["baz"],
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        for case in cases:
            assert not case.masked

        # without the baz option, the `np` parameter will not be expanded so we will be left with
        # three test cases and one analyze.  The analyze will not be masked because the `np`
        # parameter is never expanded
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 4
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert not cases[-1].masked

        # with np<3, some of the cases will be filtered
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            on_options=["baz"],
            parameter_expr="np < 3",
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert cases[-1].masked
        for case in cases[:-1]:
            assert isinstance(case, tc.TestCase)
            if case.processors == 3:
                assert case.masked
            else:
                assert not case.masked


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
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            on_options=["baz"],
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        for case in cases:
            assert not case.masked

        # without the baz option, the `np` parameter will not be expanded so we will be left with
        # three test cases and one analyze.  The analyze will not be masked because the `np`
        # parameter is never expanded
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 4
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert not cases[-1].masked

        # with np<3, some of the cases will be filtered
        cases = file.lock(
            cpus=[0, 10],
            gpus=[0, 0],
            nodes=[0, 1],
            keyword_expr="test and unit",
            on_options=["baz"],
            parameter_expr="np < 3",
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert cases[-1].masked
        for case in cases[:-1]:
            assert isinstance(case, tc.TestCase)
            if case.processors == 3:
                assert case.masked
            else:
                assert not case.masked
