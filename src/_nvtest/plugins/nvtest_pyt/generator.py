import fnmatch
import glob
import io
import os
import sys
from string import Template
from types import ModuleType
from typing import Any
from typing import Sequence

import _nvtest.config as config
import _nvtest.when as m_when
import nvtest
from _nvtest import enums
from _nvtest.error import diff_exit_status
from _nvtest.generator import AbstractTestGenerator
from _nvtest.paramset import ParameterSet
from _nvtest.test.case import TestCase
from _nvtest.test.case import TestMultiCase
from _nvtest.third_party.color import colorize
from _nvtest.third_party.monkeypatch import monkeypatch
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.time import time_in_seconds

WhenType = str | dict[str, str]


class FilterNamespace:
    def __init__(
        self,
        value: Any,
        *,
        when: WhenType | None = None,
        expect: int | None = None,
        result: str | None = None,
        action: str | None = None,
        **kwargs: Any,
    ):
        self.value: Any = value
        self.when = m_when.When.factory(when)
        self.expect = expect
        self.result = result
        self.action = action
        for key, val in kwargs.items():
            setattr(self, key, val)

    def enabled(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        result = self.when.evaluate(
            testname=testname, on_options=on_options, parameters=parameters
        )
        return result.value


class PYTTestFile(AbstractTestGenerator):
    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.owners: list[str] = []
        self._keywords: list[FilterNamespace] = []
        self._paramsets: list[FilterNamespace] = []
        self._attributes: list[FilterNamespace] = []
        self._names: list[FilterNamespace] = []
        self._timeout: list[FilterNamespace] = []
        self._generate_composite_base_case: list[FilterNamespace] = []
        self._sources: list[FilterNamespace] = []
        self._baseline: list[FilterNamespace] = []
        self._enable: list[FilterNamespace] = []
        self._preload: FilterNamespace | None = None
        self._modules: list[FilterNamespace] = []
        self._rcfiles: list[FilterNamespace] = []
        self._artifacts: list[FilterNamespace] = []
        self._depends_on: list[FilterNamespace] = []
        self._skipif_reason: str | None = None
        self._exclusive: FilterNamespace | None = None
        self._xstatus: FilterNamespace | None = None
        self._stages: set[str] = {"run"}
        self.load()

    def __repr__(self) -> str:
        return self.file

    def describe(self, on_options: list[str] | None = None) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Keywords: {', '.join(self.keywords())}\n")
        if self._sources:
            file.write("Source files:\n")
            grouped: dict[str, list[tuple[str, str]]] = {}
            for ns in self._sources:
                assert isinstance(ns.action, str)
                src, dst = ns.value
                grouped.setdefault(ns.action, []).append((src, dst))
            for action, files in grouped.items():
                file.write(f"  {action.title()}:\n")
                for src, dst in files:
                    file.write(f"    {src}")
                    if dst and dst != os.path.basename(src):
                        file.write(f" -> {dst}")
                    file.write("\n")
        cases: list[TestCase] = self.lock(on_options=on_options)
        file.write(f"{len(cases)} test case{'' if len(cases) <= 1 else 's'}:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def lock(self, on_options: list[str] | None = None) -> list[TestCase]:
        try:
            cases = self._lock(on_options=on_options)
            return cases
        except Exception as e:
            if config.debug:
                raise
            raise ValueError(f"Failed to lock {self.file}: {e}") from None

    def _lock(self, on_options: list[str] | None = None) -> list[TestCase]:
        testcases: list[TestCase] = []

        names = ", ".join(self.names())
        logging.debug(f"Generating test cases for {self} using the following test names: {names}")
        for name in self.names():
            test_mask = self.skipif_reason
            enabled, reason = self.enable(testname=name, on_options=on_options)
            if not enabled and test_mask is None:
                test_mask = f"deselected due to {reason}"
                logging.debug(f"{self}::{name} has been disabled")

            cases: list[TestCase] = []
            paramsets = self.paramsets(testname=name, on_options=on_options)
            for parameters in ParameterSet.combine(paramsets) or [{}]:
                keywords = self.keywords(testname=name, parameters=parameters)
                modules = self.modules(testname=name, on_options=on_options, parameters=parameters)
                case = TestCase(
                    self.root,
                    self.path,
                    family=name,
                    keywords=keywords,
                    parameters=parameters,
                    timeout=self.timeout(testname=name, parameters=parameters),
                    baseline=self.baseline(testname=name, parameters=parameters),
                    sources=self.sources(testname=name, parameters=parameters),
                    xstatus=self.xstatus(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    preload=self.preload(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    rcfiles=self.rcfiles(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    modules=[_[0] for _ in modules],
                    owners=self.owners,
                    artifacts=self.artifacts(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    exclusive=self.exclusive(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    stages=self.stages,
                )
                case.launcher = sys.executable
                if test_mask is not None:
                    case.mask = test_mask
                if any([_[1] is not None for _ in modules]):
                    mp = [_.strip() for _ in os.getenv("MODULEPATH", "").split(":") if _.split()]
                    for _, use in modules:
                        if use:
                            mp.insert(0, use)
                    case.add_default_env(MODULEPATH=":".join(mp))
                attributes = self.attributes(
                    testname=name, on_options=on_options, parameters=parameters
                )
                for attr, value in attributes.items():
                    case.set_attribute(attr, value)
                dependencies = self.depends_on(testname=name, parameters=parameters)
                if dependencies:
                    case.add_dependency(*dependencies)
                cases.append(case)

            generate_composite_base_case = self.generate_composite_base_case(
                testname=name, on_options=on_options
            )
            if generate_composite_base_case:
                # add previous cases as dependencies
                modules = self.modules(testname=name, on_options=on_options)
                parent = TestMultiCase(
                    self.root,
                    self.path,
                    paramsets=paramsets,
                    flag=generate_composite_base_case,
                    family=name,
                    keywords=self.keywords(testname=name),
                    timeout=self.timeout(testname=name),
                    baseline=self.baseline(testname=name),
                    sources=self.sources(testname=name),
                    xstatus=self.xstatus(testname=name, on_options=on_options),
                    preload=self.preload(testname=name, on_options=on_options),
                    modules=[_[0] for _ in modules],
                    rcfiles=self.rcfiles(testname=name, on_options=on_options),
                    owners=self.owners,
                    artifacts=self.artifacts(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    exclusive=self.exclusive(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    stages=self.stages,
                )
                parent.launcher = sys.executable
                if test_mask is not None:
                    case.mask = test_mask
                if any([_[1] is not None for _ in modules]):
                    mp = [_.strip() for _ in os.getenv("MODULEPATH", "").split(":") if _.split()]
                    for _, use in modules:
                        if use:
                            mp.insert(0, use)
                    parent.add_default_env(MODULEPATH=":".join(mp))
                for case in cases:
                    parent.add_dependency(case)
                cases.append(parent)

            testcases.extend(cases)
        self.resolve_dependencies(testcases)
        return testcases

    @staticmethod
    def resolve_dependencies(cases: list[TestCase]) -> None:
        logging.debug("Resolving dependencies in test file")
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

    @property
    def stages(self) -> list[str]:
        std_stages = {"run": 0, "post-process": 1, "post": 1, "analyze": 2, "baseline": 3}
        return sorted(self._stages, key=lambda s: (std_stages.get(s, 100), s[0]))

    @stages.setter
    def stages(self, arg: Sequence[str]) -> None:
        self._stages.update(arg)

    @property
    def skipif_reason(self) -> str | None:
        return self._skipif_reason

    @skipif_reason.setter
    def skipif_reason(self, arg: str) -> None:
        self._skipif_reason = arg

    def keywords(
        self,
        testname: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[str]:
        keywords: set[str] = set()
        for ns in self._keywords:
            result = ns.when.evaluate(testname=testname, parameters=parameters)
            if not result.value:
                continue
            keywords.update(ns.value)
        return sorted(keywords)

    def xstatus(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> int:
        if self._xstatus is not None:
            result = self._xstatus.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                return self._xstatus.value
        return 0

    def preload(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str | None:
        if self._preload is not None:
            result = self._preload.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                return self._preload.value
        return None

    def modules(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[tuple[str, str | None]]:
        modules: list[tuple[str, str | None]] = []
        for ns in self._modules:
            result = ns.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                modules.append((ns.value, getattr(ns, "use", None)))  # type: ignore
        return modules

    def rcfiles(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[str]:
        rcfiles: list[str] = []
        for ns in self._rcfiles:
            result = ns.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                rcfiles.append(ns.value)
        return rcfiles

    def artifacts(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        for ns in self._artifacts:
            result = ns.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                artifacts.append({"file": ns.value, "when": getattr(ns, "upon", "always")})
        return artifacts

    def exclusive(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        if self._exclusive is not None:
            result = self._exclusive.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                return True
        return False

    def paramsets(
        self, testname: str | None = None, on_options: list[str] | None = None
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
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
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

    def generate_composite_base_case(
        self, testname: str | None = None, on_options: list[str] | None = None
    ) -> str:
        for ns in self._generate_composite_base_case:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if not result.value:
                continue
            return ns.value
        return ""

    def timeout(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> float | None:
        for ns in self._timeout:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            return float(ns.value)
        return None

    def enable(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        for ns in self._enable:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if ns.value is True and not result.value:
                return False, result.reason
            elif ns.value is False and result.value:
                reason = result.reason or colorize("@*{enable=False}")
                return False, reason
        return True, None

    def baseline(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list[str | tuple[str, str]]:
        baseline: list[str | tuple[str, str]] = []
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
            if isinstance(ns.value, str):
                flag = ns.value
                baseline.append(flag)
            else:
                arg1, arg2 = ns.value
                file1 = self.safe_substitute(arg1, **kwds)
                if not arg2:
                    arg2 = os.path.basename(file1)
                file2 = self.safe_substitute(arg2, **kwds)
                baseline.append((file1, file2))
        return baseline

    def sources(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, list[tuple[str, str | None]]]:
        kwds = dict(parameters) if parameters else {}
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        sources: dict[str, list[tuple[str, str | None]]] = {}
        dirname = os.path.join(self.root, os.path.dirname(self.path))
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
                f = os.path.join(dirname, src)
                if os.path.exists(f):
                    sources.setdefault(ns.action, []).append((src, None))
                else:
                    files = glob.glob(f)
                    for file in files:
                        # keep paths relative to dirname
                        file = os.path.relpath(file, dirname)
                        sources.setdefault(ns.action, []).append((file, None))
            else:
                dst = self.safe_substitute(dst, **kwds)
                src, dst = [os.path.relpath(p, dirname) for p in (src, dst)]
                sources.setdefault(ns.action, []).append((src, dst))
        return sources

    def depends_on(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
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

    def m_keywords(self, *args: str, when: WhenType | None = None) -> None:
        keyword_ns = FilterNamespace(tuple(args), when=when)
        self._keywords.append(keyword_ns)

    def m_xfail(self, *, code: int = -1, when: WhenType | None = None) -> None:
        ns = FilterNamespace(code, when=when)
        self._xstatus = ns

    def m_xdiff(self, *, when: WhenType | None = None) -> None:
        ns = FilterNamespace(diff_exit_status, when=when)
        self._xstatus = ns

    def m_owners(self, *args: str) -> None:
        self.owners.extend(args)

    def m_depends_on(
        self,
        arg: str,
        when: WhenType | None = None,
        result: str | None = None,
        expect: int | None = None,
    ) -> None:
        ns = FilterNamespace(arg, when=when, result=result, expect=expect)
        self._depends_on.append(ns)

    def m_preload(self, arg: str, when: WhenType | None = None) -> None:
        ns = FilterNamespace(arg, when=when)
        self._preload = ns

    def m_module(self, arg: str, when: WhenType | None = None, use: str | None = None) -> None:
        ns = FilterNamespace(arg, when=when, use=use)
        self._modules.append(ns)

    def m_rcfile(self, arg: str, when: WhenType | None = None) -> None:
        ns = FilterNamespace(arg, when=when)
        self._rcfiles.append(ns)

    def m_artifact(self, file: str, when: WhenType | None = None, upon: str = "always") -> None:
        ns = FilterNamespace(file, when=when, upon=upon)
        self._artifacts.append(ns)

    def m_exclusive(self, when: WhenType | None = None) -> None:
        ns = FilterNamespace(True, when=when)
        self._exclusive = ns

    def m_parameterize(
        self,
        argnames: str | Sequence[str],
        argvalues: list[Sequence[Any] | Any],
        when: WhenType | None = None,
        type: enums.enums | None = None,
        samples: int = 10,
    ) -> None:
        type = type or enums.list_parameter_space
        if not isinstance(type, enums.enums):
            raise ValueError(
                f"{self.path}: parameterize: type: expected "
                f"nvtest.enums, got {type.__class__.__name__}"
            )
        if type is enums.centered_parameter_space:
            pset = ParameterSet.centered_parameter_space(argnames, argvalues, file=self.file)
        elif type is enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                argnames, argvalues, samples=samples, file=self.file
            )
        else:
            pset = ParameterSet.list_parameter_space(
                argnames,
                argvalues,
                file=self.file,
            )
        for row in pset:
            for i, (key, value) in enumerate(row):
                if key in ("np", "ngpu", "ndevice", "nnode"):
                    if not isinstance(value, int):
                        raise ValueError(
                            f"{self.path}: parameterize: expected {key}={value} to be an int"
                        )
                    elif value < 0:
                        raise ValueError(
                            f"{self.path}: parameterize: expected {key}={value} to be >= 0"
                        )
        ns = FilterNamespace(pset, when=when)
        self._paramsets.append(ns)

    def m_set_attribute(self, when: WhenType | None = None, **kwargs: Any) -> None:
        ns = FilterNamespace(kwargs, when=when)
        self._attributes.append(ns)

    def add_sources(
        self,
        action: str,
        *files: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        if src is not None:
            if files:
                raise ValueError(
                    "positional file arguments incompatible with "
                    "explicit src and dst keyword arguments"
                )
            ns = FilterNamespace((src, dst), action=action, when=when)
            self._sources.append(ns)
            return
        for file in files:
            ns = FilterNamespace((file, None), action=action, when=when)
            self._sources.append(ns)

    def m_copy(
        self,
        *files: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        self.add_sources("copy", *files, src=src, dst=dst, when=when)

    def m_link(
        self,
        *files: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        self.add_sources("link", *files, src=src, dst=dst, when=when)

    def m_sources(
        self,
        *files: str,
        when: WhenType | None = None,
    ) -> None:
        self.add_sources("sources", *files, when=when)

    def m_stages(self, *args: str) -> None:
        # For now just pass through, could add a when statement?
        self._stages.update(args)

    def m_generate_composite_base_case(
        self,
        *,
        flag: str | None = None,
        script: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        if flag is not None and script is not None:
            raise ValueError(
                "PYTTestFile.generate_composite_base_case: 'script' and 'flag' keyword arguments are mutually exclusive"
            )
        if script is not None:
            string = script
        else:
            string = flag or "--base"
        ns = FilterNamespace(string, when=when)
        self._generate_composite_base_case.append(ns)

    def m_name(self, arg: str) -> None:
        self._names.append(FilterNamespace(arg))

    def m_timeout(
        self,
        arg: str | float | int,
        when: WhenType | None = None,
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
        when: WhenType | None = None,
    ) -> None:
        ns = FilterNamespace(bool(arg), when=when)
        self._enable.append(ns)

    def m_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
        flag: str | None = None,
    ) -> None:
        ns: FilterNamespace
        if (src is not None) or (dst is not None):
            if src is None:
                raise TypeError(
                    "PYTTestFile.baseline: missing required positional argument: `src`"
                )
            if dst is None:
                raise TypeError(
                    "PYTTestFile.baseline: missing required positional argument: `dst`"
                )
            if flag is not None:
                raise ValueError(
                    "PYTTestFile.baseline: 'src/dst' and 'flag' keyword arguments are mutually exclusive"
                )
            ns = FilterNamespace((src, dst), when=when)
        elif flag is not None:
            ns = FilterNamespace(flag, when=when)
        else:
            raise ValueError(
                "PYTTestFile.baseline: missing required argument 'src'/'dst' or 'flag'"
            )
        self._baseline.append(ns)
        self._stages.add("baseline")

    def load(self):
        import _nvtest

        try:
            # Replace functions in the dummy nvtest.directives module with
            # instance methods of this test file so that calls to the directives
            # are passed to this test
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
        elif fnmatch.fnmatch(os.path.basename(path), "nvtest_*.py"):
            return True
        return False

    def f_generate_composite_base_case(
        self,
        *,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
    ):
        self.m_generate_composite_base_case(when=when, flag=flag, script=script)

    def f_analyze(
        self,
        *,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
    ):
        # vvtest compatibility
        if script is None and flag is None:
            flag = "--analyze"
        self.m_generate_composite_base_case(when=when, flag=flag, script=script)

    def f_copy(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ):
        self.m_copy(*args, src=src, dst=dst, when=when)

    def f_depends_on(
        self,
        arg: str,
        when: WhenType | None = None,
        expect: int | None = None,
        result: str | None = None,
    ):
        self.m_depends_on(arg, when=when, result=result, expect=expect)

    def f_gpus(self, *ngpus: int, when: WhenType | None = None) -> None:
        self.m_parameterize("ngpu", list(ngpus), when=when)

    def f_cpus(self, *values: int, when: WhenType | None = None) -> None:
        self.m_parameterize("np", list(values), when=when)

    def f_processors(self, *values: int, when: WhenType | None = None) -> None:
        self.m_parameterize("np", list(values), when=when)

    def f_nodes(self, *values: int, when: WhenType | None = None) -> None:
        self.m_parameterize("nnode", list(values), when=when)

    def f_enable(self, *args: bool, when: WhenType | None = None):
        arg = True if not args else args[0]
        self.m_enable(arg, when=when)

    def f_keywords(self, *args: str, when: WhenType | None = None) -> None:
        self.m_keywords(*args, when=when)

    def f_link(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ):
        self.m_link(*args, src=src, dst=dst, when=when)

    def f_owners(self, *args: str):
        self.m_owners(*args)

    def f_owner(self, arg: str):
        self.m_owners(arg)

    def f_parameterize(
        self,
        names: str | Sequence[str],
        values: list[Sequence[Any] | Any],
        *,
        when: WhenType | None = None,
        type: enums.enums = enums.list_parameter_space,
        samples: int = 10,
    ) -> None:
        self.m_parameterize(names, values, when=when, type=type, samples=samples)

    def f_preload(self, arg: str, *, when: WhenType | None = None) -> None:
        self.m_preload(arg, when=when)

    def f_load_module(
        self, arg: str, *, when: WhenType | None = None, use: str | None = None
    ) -> None:
        self.m_module(arg, when=when, use=use)

    def f_source(self, arg: str, *, when: WhenType | None = None):
        self.m_rcfile(arg, when=when)

    def f_artifact(self, file: str, *, when: WhenType | None = None, upon: str = "always") -> None:
        if upon not in ("always", "success", "failure"):
            raise ValueError("upon: invalid value, choose from 'always', 'success', 'failure'")
        self.m_artifact(file, when=when, upon=upon)

    def f_exclusive(self, *, when: WhenType | None = None) -> None:
        self.m_exclusive(when=when)

    def f_set_attribute(self, *, when: WhenType | None = None, **attributes: Any) -> None:
        self.m_set_attribute(when=when, **attributes)

    def f_skipif(self, arg: bool, *, reason: str) -> None:
        self.m_skipif(arg, reason=reason)

    def f_sources(self, *args: str, when: WhenType | None = None):
        self.m_sources(*args, when=when)

    def f_stages(self, *args: str):
        self.m_stages(*args)

    def f_testname(self, arg: str) -> None:
        self.m_name(arg)

    f_name = f_testname

    def f_timeout(self, arg: str | float | int, *, when: WhenType | None = None):
        self.m_timeout(arg, when=when)

    def f_xdiff(self, *, when: WhenType | None = None):
        self.m_xdiff(when=when)

    def f_xfail(self, *, code: int = -1, when: WhenType | None = None):
        self.m_xfail(code=code, when=when)

    def f_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
        flag: str | None = None,
    ) -> None:
        self.m_baseline(src, dst, when=when, flag=flag)
