from typing import TYPE_CHECKING
from typing import Iterable
from typing import Optional
from typing import Sequence
from typing import Union

if TYPE_CHECKING:
    from _nvtest.test.testfile import AbstractTestFile


class Directive:
    def __init__(self, testfile: "AbstractTestFile") -> None:
        self.testfile = testfile

    def keywords(
        self,
        *args: str,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
    ) -> None:
        self.testfile.m_keywords(*args, parameters=parameters, testname=testname)

    def parameterize(
        self,
        names: Union[str, Sequence[str]],
        values: Iterable[Union[Sequence[object], object]],
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
    ) -> None:
        self.testfile.m_parameterize(
            names, values, options=options, platforms=platforms, testname=testname
        )

    def depends_on(
        self,
        arg: str,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
        expect: Optional[int] = None,
        result: Optional[str] = None,
    ):
        self.testfile.m_depends_on(
            arg, testname=testname, result=result, expect=expect, parameters=parameters
        )

    def analyze(
        self,
        arg: bool = True,
        *,
        flag: Optional[str] = None,
        script: Optional[str] = None,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
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

    testname = name

    def timeout(
        self,
        arg: Union[str, float, int],
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
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
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
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
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
    ):
        self.testfile.m_link(
            *args,
            rename=rename,
            options=options,
            platforms=platforms,
            parameters=parameters,
            testname=testname,
        )

    def sources(self, *args: str, testname: Optional[str] = None):
        self.testfile.m_sources(*args, testname=testname)

    def enable(
        self,
        arg: bool,
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
    ):
        self.testfile.m_enable(
            arg, options=options, platforms=platforms, testname=testname
        )

    def preload(
        self,
        arg: str,
        *,
        source: bool = False,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
    ):
        self.testfile.m_preload(
            arg,
            source=source,
            options=options,
            platforms=platforms,
            testname=testname,
            parameters=parameters,
        )


class DummyDirective:
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

    def preload(self, *args, **kwargs):
        ...
