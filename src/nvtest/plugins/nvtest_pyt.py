import fnmatch
import os
from types import ModuleType
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

import nvtest
from _nvtest import enums
from _nvtest.test.generator import AbstractTestFile
from _nvtest.third_party.monkeypatch import monkeypatch


class PYTTestFile(AbstractTestFile):
    def load(self):
        import _nvtest

        try:
            m = ModuleType("directives")
            m.__file__ = f"{m.__name__}.py"
            for item in dir(self):
                if item.startswith("f_"):
                    setattr(m, item[2:], getattr(self, item))
            _nvtest.FILE_SCANNING = True
            with monkeypatch.context() as mp:
                mp.setattr(nvtest, "directives", m)
                code = compile(open(self.file).read(), self.file, "exec")
                global_vars = {"__name__": "__load__", "__file__": self.file}
                try:
                    exec(code, global_vars)
                except SystemExit:
                    pass
        finally:
            _nvtest.FILE_SCANNING = False

    @classmethod
    def matches(cls, path: str) -> bool:
        if path.endswith(".pyt"):
            return True
        elif fnmatch.fnmatch(os.path.basename(path), "*.nvtest.py"):
            return True
        return False

    def f_analyze(
        self,
        *,
        when: Optional[str] = None,
        flag: Optional[str] = None,
        script: Optional[str] = None,
    ):
        self.m_analyze(when=when, flag=flag, script=script)

    def f_copy(self, *args: str, when: Optional[str] = None, rename: bool = False):
        self.m_copy(*args, rename=rename, when=when)

    def f_depends_on(
        self,
        arg: str,
        when: Optional[str] = None,
        expect: Optional[int] = None,
        result: Optional[str] = None,
    ):
        self.m_depends_on(arg, when=when, result=result, expect=expect)

    def f_gpus(self, *ngpus: int, when: Optional[str] = None) -> None:
        self.m_parameterize("ngpu", list(ngpus), when=when)

    def f_enable(self, *args: bool, when: Optional[str] = None):
        arg = True if not args else args[0]
        self.m_enable(arg, when=when)

    def f_keywords(self, *args: str, when: Optional[str] = None) -> None:
        self.m_keywords(*args, when=when)

    def f_link(self, *args: str, when: Optional[str] = None, rename: bool = False):
        self.m_link(*args, rename=rename, when=when)

    def f_owners(self, *args: str):
        self.m_owners(*args)

    def f_parameterize(
        self,
        names: Union[str, Sequence[str]],
        values: list[Union[Sequence[object], object]],
        *,
        when: Optional[str] = None,
        type: enums.enums = enums.list_parameter_space,
    ) -> None:
        self.m_parameterize(names, values, when=when, type=type)

    def f_preload(self, arg: str, *, when: Optional[str] = None, source: bool = False):
        self.m_preload(arg, when=when, source=source)

    def f_processors(self, *values: int, when: Optional[str] = None) -> None:
        self.m_parameterize("np", list(values), when=when)

    def f_set_attribute(self, *, when: Optional[str] = None, **attributes: Any) -> None:
        self.m_set_attribute(when=when, **attributes)

    def f_skipif(self, arg: bool, *, reason: str) -> None:
        self.m_skipif(arg, reason=reason)

    def f_sources(self, *args: str, when: Optional[str] = None):
        self.m_sources(*args, when=when)

    def f_testname(self, arg: str) -> None:
        self.m_name(arg)

    f_name = f_testname

    def f_timeout(self, arg: Union[str, float, int], *, when: Optional[str] = None):
        self.m_timeout(arg, when=when)

    def f_xdiff(self, *, when: Optional[str] = None):
        self.m_xdiff(when=when)

    def f_xfail(self, *, code: int = -1, when: Optional[str] = None):
        self.m_xfail(code=code, when=when)


nvtest.plugin.test_generator(PYTTestFile)
