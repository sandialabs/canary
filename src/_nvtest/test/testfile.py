import errno
import fnmatch
import glob
import os
from string import Template
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

import _nvtest.directives.enums as d_enums

from .. import config
from ..compat.vvtest import load_vvt
from ..directives.match import deselect_by_keyword
from ..directives.match import deselect_by_parameter
from ..directives.parameter_set import ParameterSet
from ..directives.when import When
from ..util import tty
from ..util.filesystem import working_dir
from ..util.time import time_in_seconds
from ..util.tty.color import colorize
from .testcase import TestCase


class FilterNamespace:
    def __init__(
        self,
        value: Any,
        *,
        when: Optional[Union[str, bool]] = None,
        expect: Optional[int] = None,
        result: Optional[str] = None,
        action: Optional[str] = None,
    ):
        self.value: Any = value
        self.when = When(when)
        self.expect = expect
        self.result = result
        self.action = action

    def enabled(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> bool:
        result = self.when.evaluate(
            testname=testname, on_options=on_options, parameters=parameters
        )
        return result.value


class AbstractTestFile:
    """The AbstractTestFile is an object representing a test file

    Parameters
    ----------
    root : str
        The base test directory, or file path if ``path`` is not given
    path : str
        The file path, relative to root

    Notes
    -----
    The ``AbstractTestFile`` represents of an abstract test object.  The
    ``AbstractTestFile`` facilitates the creation and management of ``TestCase``s
    based on a user-defined configuration.

    Examples
    --------
    >>> file = AbstractTestFile(root, path)
    >>> cases = file.freeze()

    """

    def __init__(self, root: str, path: Optional[str] = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = os.path.abspath(root)
        self.path = path
        self.file = os.path.join(self.root, self.path)
        if not os.path.exists(self.file):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = os.path.splitext(os.path.basename(self.path))[0]
        self._keywords: list[FilterNamespace] = []
        self._paramsets: list[FilterNamespace] = []
        self._attributes: list[FilterNamespace] = []
        self._names: list[FilterNamespace] = []
        self._timeout: list[FilterNamespace] = []
        self._analyze: list[FilterNamespace] = []
        self._sources: list[FilterNamespace] = []
        self._baseline: list[FilterNamespace] = []
        self._enable: list[FilterNamespace] = []
        self._preload: list[FilterNamespace] = []
        self._depends_on: list[FilterNamespace] = []
        self.skipif_reason: Optional[str] = None

        self.load()

    def __repr__(self):
        return self.path

    def load(self):
        if self.path.endswith(".vvt"):
            load_vvt(self)
        else:
            self._load()

    @property
    def type(self):
        return "vvt" if os.path.splitext(self.file)[1] == ".vvt" else "pyt"

    def _load(self):
        import _nvtest

        file = self.file
        code = compile(open(file).read(), file, "exec")
        global_vars = {"__name__": "__load__", "__file__": file, "__testfile__": self}
        _nvtest.FILE_SCANNING = True
        try:
            exec(code, global_vars)
        finally:
            _nvtest.FILE_SCANNING = False

    def freeze(
        self,
        cpu_count: Optional[int] = None,
        device_count: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
    ) -> list[TestCase]:
        try:
            return self._freeze(
                cpu_count=cpu_count,
                device_count=device_count,
                keyword_expr=keyword_expr,
                on_options=on_options,
                parameter_expr=parameter_expr,
            )
        except Exception as e:
            if tty.HAVE_DEBUG:
                raise
            raise ValueError(f"Failed to freeze {self.file}: {e}") from None

    def _freeze(
        self,
        cpu_count: Optional[int] = None,
        device_count: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
    ) -> list[TestCase]:
        cpu_count = cpu_count or config.get("machine:cpu_count")
        device_count = device_count or config.get("machine:device_count")
        testcases: list[TestCase] = []
        names = ", ".join(self.names())
        tty.verbose(
            f"Generating test cases for {self} using the following test names: {names}"
        )
        for name in self.names():
            mask = self.skipif_reason
            enabled, reason = self.enable(testname=name, on_options=on_options)
            if not enabled and mask is None:
                mask = f"deselected due to {reason}"
                tty.verbose(f"{self}::{name} has been disabled")
            cases: list[TestCase] = []
            paramsets = self.paramsets(testname=name, on_options=on_options)
            for parameters in ParameterSet.combine(paramsets) or [{}]:
                keywords = self.keywords(testname=name, parameters=parameters)
                if mask is None and keyword_expr is not None:
                    kwds = {kw for kw in keywords}
                    kwds.add(name)
                    kwds.update(parameters.keys())
                    kwds.update({"staged"})
                    kw_mask = deselect_by_keyword(kwds, keyword_expr)
                    if kw_mask:
                        tty.verbose(f"Skipping {self}::{name}")
                        mask = colorize("deselected by @*b{keyword expression}")

                np = parameters.get("np")
                if not isinstance(np, int) and np is not None:
                    class_name = np.__class__.__name__
                    raise ValueError(
                        f"{self.name}: expected np={np} to be an int, not {class_name}"
                    )
                if mask is None and np and np > cpu_count:
                    s = "deselected due to @*b{exceeding cpu count of machine}"
                    mask = colorize(s)
                nd = parameters.get("ndevice")
                if not isinstance(nd, int) and nd is not None:
                    class_name = nd.__class__.__name__
                    raise ValueError(
                        f"{self.name}: expected ndevice={nd} "
                        f"to be an int, not {class_name}"
                    )
                if mask is None and nd and nd > device_count:
                    s = "deselected due to @*b{exceeding device count of machine}"
                    mask = colorize(s)
                if mask is None and ("TDD" in keywords or "tdd" in keywords):
                    mask = colorize("deselected due to @*b{TDD keyword}")
                if mask is None and parameter_expr:
                    param_mask = deselect_by_parameter(parameters, parameter_expr)
                    if param_mask:
                        mask = colorize("deselected due to @*b{parameter expression}")
                attributes = self.attributes(
                    testname=name, on_options=on_options, parameters=parameters
                )

                case = TestCase(
                    self.root,
                    self.path,
                    family=name,
                    keywords=keywords,
                    parameters=parameters,
                    timeout=self.timeout(testname=name, parameters=parameters),
                    baseline=self.baseline(testname=name, parameters=parameters),
                    sources=self.sources(testname=name, parameters=parameters),
                )
                if mask is not None:
                    case.mask = mask
                for (attr, value) in attributes.items():
                    case.set_attribute(attr, value)
                cases.append(case)

            analyze = self.analyze(testname=name, on_options=on_options)
            if analyze:
                # add previous cases as dependencies
                mask_analyze_case: Optional[str] = None
                if all(case.masked for case in cases):
                    mask_analyze_case = "deselected due to skipped dependencies"
                parent = TestCase(
                    self.root,
                    self.path,
                    family=name,
                    analyze=analyze,
                    keywords=self.keywords(testname=name),
                    timeout=self.timeout(testname=name),
                    baseline=self.baseline(testname=name),
                    sources=self.sources(testname=name),
                )
                if mask_analyze_case is not None:
                    parent.mask = mask_analyze_case
                for case in cases:
                    parent.add_dependency(case)
                cases.append(parent)
            dependencies = self.depends_on(testname=name, parameters=parameters)
            if dependencies:
                for case in cases:
                    case.add_dependency(*dependencies)
            testcases.extend(cases)
        self.resolve_dependencies(testcases)
        return testcases

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        tty.verbose("Resolving dependencies in test file")
        case_map = dict([(case.name, i) for (i, case) in enumerate(cases)])
        for i, case in enumerate(cases):
            for j, pat in enumerate(case.dep_patterns):
                matches = [
                    cases[k]
                    for (name, k) in case_map.items()
                    if i != k and fnmatch.fnmatchcase(name, pat)
                ]
                if matches:
                    case.dep_patterns[j] = "null"
                    for match in matches:
                        case.add_dependency(match)
            case.dep_patterns = [_ for _ in case.dep_patterns if _ != "null"]

    # -------------------------------------------------------------------------------- #

    def keywords(
        self,
        testname: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        keywords: set[str] = set()
        for ns in self._keywords:
            result = ns.when.evaluate(testname=testname, parameters=parameters)
            if not result.value:
                continue
            keywords.update(ns.value)
        return sorted(keywords)

    def paramsets(
        self, testname: Optional[str] = None, on_options: Optional[list[str]] = None
    ) -> list[ParameterSet]:
        paramsets: list[ParameterSet] = []
        for ns in self._paramsets:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if not result.value:
                continue
            paramsets.append(ns.value)
        return paramsets

    def attributes(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        for ns in self._attributes:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            attributes.update(ns.value)
        return attributes

    def names(self) -> list[str]:
        names: list[str] = [ns.value for ns in self._names]
        if not names:
            names.append(self.name)
        return names

    def analyze(
        self, testname: Optional[str] = None, on_options: Optional[list[str]] = None
    ) -> str:
        for ns in self._analyze:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if not result.value:
                continue
            return ns.value
        return ""

    def timeout(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> Union[int, None]:
        for ns in self._timeout:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            return int(ns.value)
        return None

    def enable(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
    ) -> tuple[bool, Union[str, None]]:
        for ns in self._enable:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if ns.value is True and not result.value:
                return False, result.reason
            elif ns.value is False and result.value:
                return False, result.reason
        return True, None

    def baseline(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[tuple[str, str]]:
        baseline: list[tuple[str, str]] = []
        kwds = dict(parameters) if parameters else {}
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        for ns in self._baseline:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            arg1, arg2 = ns.value
            file1 = self.safe_substitute(arg1, **kwds)
            if not arg2:
                arg2 = os.path.basename(file1)
            file2 = self.safe_substitute(arg2, **kwds)
            baseline.append((file1, file2))
        return baseline

    def sources(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, list[tuple[str, str]]]:
        kwds = dict(parameters) if parameters else {}
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        sources: dict[str, list[tuple[str, str]]] = {}
        with working_dir(os.path.join(self.root, os.path.dirname(self.path))):
            for ns in self._sources:
                assert isinstance(ns.action, str)
                result = ns.when.evaluate(
                    testname=testname, on_options=on_options, parameters=parameters
                )
                if not result.value:
                    continue
                src, dst = ns.value
                src = self.safe_substitute(src, **kwds)
                if dst is None:
                    files = glob.glob(src)
                    for file in files:
                        dst = os.path.basename(file)
                        sources.setdefault(ns.action, []).append((file, dst))
                else:
                    dst = self.safe_substitute(dst, **kwds)
                    sources.setdefault(ns.action, []).append((src, dst))
        return sources

    def depends_on(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        kwds = dict(parameters) if parameters else {}
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        dependencies: list[str] = []
        for ns in self._depends_on:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            dependencies.append(self.safe_substitute(ns.value, **kwds))
        return dependencies

    @staticmethod
    def safe_substitute(string: str, **kwds) -> str:
        if "$" in string:
            t = Template(string)
            return t.safe_substitute(**kwds)
        return string.format(**kwds)

    # -------------------------------------------------------------------------------- #

    def m_keywords(self, *args: str, when: Optional[str] = None) -> None:
        keyword_ns = FilterNamespace(tuple(args), when=when)
        self._keywords.append(keyword_ns)

    def m_depends_on(
        self,
        arg: str,
        when: Optional[str] = None,
        result: Optional[str] = None,
        expect: Optional[int] = None,
    ) -> None:
        ns = FilterNamespace(arg, when=when, result=result, expect=expect)
        self._depends_on.append(ns)

    def m_preload(
        self, arg: str, source: bool = False, when: Optional[str] = None
    ) -> None:
        ns = FilterNamespace(arg, action="source" if source else None, when=when)
        self._preload.append(ns)

    def m_parameterize(
        self,
        argnames: Union[str, Sequence[str]],
        argvalues: list[Union[Sequence[Any], Any]],
        when: Optional[str] = None,
        type: d_enums.enums = d_enums.list_parameter_space,
    ) -> None:
        if not isinstance(type, d_enums.enums):
            raise ValueError(
                f"parameterize: type: expected "
                f"nvtest.enums, got {type.__class__.__name__}"
            )
        if type is d_enums.centered_parameter_space:
            pset = ParameterSet.centered_parameter_space(
                argnames, argvalues, file=self.file
            )
        elif type is d_enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                argnames, argvalues, file=self.file
            )
        else:
            pset = ParameterSet.list_parameter_space(
                argnames,
                argvalues,
                file=self.file,
            )
        ns = FilterNamespace(pset, when=when)
        self._paramsets.append(ns)

    def m_set_attribute(self, when: Optional[str] = None, **kwargs: Any) -> None:
        ns = FilterNamespace(kwargs, when=when)
        self._attributes.append(ns)

    def add_sources(
        self,
        action: str,
        *files: str,
        rename: bool = False,
        when: Optional[str] = None,
    ) -> None:
        dst: Union[None, str] = None
        if rename:
            try:
                src, dst = files
            except ValueError:
                raise ValueError("Expected 2 file arguments with rename=True") from None
            ns = FilterNamespace((src, dst), action=action, when=when)
            self._sources.append(ns)
            return
        for file in files:
            ns = FilterNamespace((file, None), action=action, when=when)
            self._sources.append(ns)

    def m_copy(
        self,
        *files: str,
        when: Optional[str] = None,
    ) -> None:
        self.add_sources("copy", *files, when=when)

    def m_link(
        self, *files: str, rename: bool = False, when: Optional[str] = None
    ) -> None:
        self.add_sources("link", *files, rename=rename, when=when)

    def m_sources(
        self,
        *files: str,
        when: Optional[str] = None,
    ) -> None:
        self.add_sources("sources", *files, when=when)

    def m_analyze(
        self,
        arg: Optional[bool] = True,
        *,
        flag: Optional[str] = None,
        script: Optional[str] = None,
        when: Optional[str] = None,
    ) -> None:
        if flag is not None and script is not None:
            raise ValueError(
                "TestFile.analyze: 'script' and 'flag' "
                "keyword arguments are mutually exclusive"
            )
        if not arg:
            return
        if script is not None:
            string = script
        else:
            string = flag or "--analyze"
        ns = FilterNamespace(string, when=when)
        self._analyze.append(ns)

    def m_name(self, arg: str) -> None:
        self._names.append(FilterNamespace(arg))

    def m_timeout(
        self,
        arg: Union[str, float, int],
        when: Optional[str] = None,
    ) -> None:
        "testname parameter parameters platform platforms option options"
        arg = time_in_seconds(arg)
        ns = FilterNamespace(arg, when=when)
        self._timeout.append(ns)

    def m_skipif(self, arg: bool, *, reason: str) -> None:
        if arg:
            self.skipif_reason = reason

    def m_enable(
        self,
        arg: bool,
        when: Optional[str] = None,
    ) -> None:
        ns = FilterNamespace(bool(arg), when=when)
        self._enable.append(ns)

    def m_baseline(
        self,
        arg1: str,
        arg2: Optional[str] = None,
        when: Optional[str] = None,
    ) -> None:
        ns = FilterNamespace((arg1, arg2), when=when)
        self._baseline.append(ns)


class UsageError(Exception):
    pass
