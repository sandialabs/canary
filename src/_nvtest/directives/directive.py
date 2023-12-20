from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

from . import enums

if TYPE_CHECKING:
    from _nvtest.test.testfile import AbstractTestFile


class Directive:
    """"""

    def __init__(self, testfile: "AbstractTestFile") -> None:
        self.testfile = testfile

    def keywords(self, *args: str, when: Optional[str] = None) -> None:
        self.testfile.m_keywords(*args, when=when)

    def parameterize(
        self,
        names: Union[str, Sequence[str]],
        values: list[Union[Sequence[object], object]],
        *,
        when: Optional[str] = None,
        type: enums.enums = enums.list_parameter_space,
    ) -> None:
        self.testfile.m_parameterize(names, values, when=when, type=type)

    def set_attribute(self, *, when: Optional[str] = None, **attributes: Any) -> None:
        self.testfile.m_set_attribute(when=when, **attributes)

    def processors(self, *values: int, when: Optional[str] = None) -> None:
        self.testfile.m_parameterize("np", list(values), when=when)

    def devices(self, *values: int, when: Optional[str] = None) -> None:
        self.testfile.m_parameterize("ndevice", list(values), when=when)

    def depends_on(
        self,
        arg: str,
        when: Optional[str] = None,
        expect: Optional[int] = None,
        result: Optional[str] = None,
    ):
        self.testfile.m_depends_on(arg, when=when, result=result, expect=expect)

    def analyze(
        self,
        arg: bool = True,
        *,
        when: Optional[str] = None,
        flag: Optional[str] = None,
        script: Optional[str] = None,
    ):
        self.testfile.m_analyze(arg=arg, when=when, flag=flag, script=script)

    def name(self, arg: str):
        self.testfile.m_name(arg)

    testname = name

    def timeout(self, arg: Union[str, float, int], *, when: Optional[str] = None):
        self.testfile.m_timeout(arg, when=when)

    def skipif(self, arg: bool, *, reason: str):
        self.testfile.m_skipif(arg, reason=reason)

    def copy(self, *args: str, when: Optional[str] = None, rename: bool = False):
        self.testfile.m_copy(*args, when=when)

    def link(self, *args: str, when: Optional[str] = None, rename: bool = False):
        self.testfile.m_link(*args, when=when, rename=rename)

    def sources(self, *args: str, when: Optional[str] = None):
        self.testfile.m_sources(*args, when=when)

    def enable(self, arg: bool, *, when: Optional[str] = None):
        self.testfile.m_enable(arg, when=when)

    def preload(self, arg: str, *, when: Optional[str] = None, source: bool = False):
        self.testfile.m_preload(arg, when=when, source=source)


class DummyDirective:
    def keywords(self, *args, **kwargs):
        ...

    def set_attribute(self, *args, **kwargs):
        ...

    def parameterize(self, *args, **kwargs):
        ...

    def processors(self, *args, **kwargs):
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
