from typing import TYPE_CHECKING
from typing import Iterable
from typing import Sequence
from typing import Union

import _nvtest.plugin as plugin
from _nvtest.config import Config
from _nvtest.config.argparsing import Parser
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.main import console_main
from _nvtest.session.base import Session
from _nvtest.test.enums import Result
from _nvtest.test.testcase import TestCase
from _nvtest.util import tty
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import which

if TYPE_CHECKING:
    from _nvtest.test.testfile import AbstractTestFile


version_info = (0, 0, 1)
version = ".".join(str(_) for _ in version_info)


class Marker:
    def __init__(self, testfile: "AbstractTestFile") -> None:
        self.testfile = testfile

    def keywords(
        self,
        *args: str,
        parameters: str = None,
        testname: str = None,
    ) -> None:
        self.testfile.m_keywords(*args, parameters=parameters, testname=testname)

    def parameterize(
        self,
        names: Union[str, Sequence[str]],
        values: Iterable[Union[Sequence[object], object]],
        *,
        options: str = None,
        platforms: str = None,
        testname: str = None,
    ) -> None:
        self.testfile.m_parameterize(
            names, values, options=options, platforms=platforms, testname=testname
        )

    def depends_on(
        self,
        arg: str,
        parameters: str = None,
        testname: str = None,
        expect: int = None,
        result: str = None,
    ):
        self.testfile.m_depends_on(
            arg, testname=testname, result=result, expect=expect, parameters=parameters
        )

    def analyze(
        self,
        arg: bool = True,
        *,
        flag: str = None,
        script: str = None,
        options: str = None,
        platforms: str = None,
        testname: str = None,
    ):
        self.testfile.m_analyze(
            arg=arg,
            flag=flag,
            script=script,
            options=options,
            platforms=platforms,
            testname=testname,
        )

    def name(self, arg: str):
        self.testfile.m_name(arg)

    def timeout(
        self,
        arg: Union[str, float, int],
        *,
        options: str = None,
        platforms: str = None,
        parameters: str = None,
        testname: str = None,
    ):
        self.testfile.m_timeout(
            arg,
            options=options,
            platforms=platforms,
            testname=testname,
            parameters=parameters,
        )

    def skipif(self, arg: bool, *, reason: str):
        self.testfile.m_skipif(arg, reason=reason)

    def copy(
        self,
        *args: str,
        options: str = None,
        platforms: str = None,
        parameters: str = None,
        testname: str = None,
    ):
        self.testfile.m_copy(
            *args,
            options=options,
            platforms=platforms,
            parameters=parameters,
            testname=testname,
        )

    def link(
        self,
        *args: str,
        rename: bool = False,
        options: str = None,
        platforms: str = None,
        parameters: str = None,
        testname: str = None,
    ):
        self.testfile.m_link(
            *args,
            rename=rename,
            options=options,
            platforms=platforms,
            parameters=parameters,
            testname=testname,
        )

    def sources(self, *args: str, testname: str = None):
        self.testfile.m_sources(*args, testname=testname)

    def enable(
        self,
        arg: bool,
        *,
        options: str = None,
        platforms: str = None,
        testname: str = None,
    ):
        self.testfile.m_enable(
            arg, options=options, platforms=platforms, testname=testname
        )


class DummyMarker:
    def keywords(self, *args, **kwargs):
        ...

    def parameterize(self, *args, **kwargs):
        ...

    def analyze(self, *args, **kwargs):
        ...

    def name(self, *args, **kwargs):
        ...

    def timeout(self, *args, **kwargs):
        ...

    def skipif(self, *args, **kwargs):
        ...

    def copy(self, *args, **kwargs):
        ...

    def link(self, *args, **kwargs):
        ...

    def sources(self, *args, **kwargs):
        ...

    def enable(self, *args, **kwargs):
        ...

    def depends_on(self, *args, **kwargs):
        ...


def __getattr__(name):
    import inspect

    import _nvtest
    from _nvtest.test.testinstance import TestInstance

    if name == "mark":
        for frame_info in inspect.stack():
            if "__testfile__" in frame_info.frame.f_globals:
                testfile = frame_info.frame.f_globals["__testfile__"]
                return Marker(testfile)
        return DummyMarker()
    elif name == "FILE_SCANNING":
        return _nvtest.FILE_SCANNING
    elif name == "test":
        test = type("", (), {})()
        test.instance = TestInstance.load()
        return test

    raise AttributeError(name)
