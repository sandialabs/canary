import fnmatch
import glob
import io
import math
import os
import sys
from string import Template
from types import ModuleType
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

import _nvtest.config as config
import _nvtest.when as m_when
import nvtest
from _nvtest import enums
from _nvtest.error import diff_exit_status
from _nvtest.paramset import ParameterSet
from _nvtest.resources import ResourceHandler
from _nvtest.test.case import TestCase
from _nvtest.test.case import TestMultiCase
from _nvtest.test.generator import TestGenerator
from _nvtest.third_party.color import colorize
from _nvtest.third_party.monkeypatch import monkeypatch
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.time import time_in_seconds


class FilterNamespace:
    def __init__(
        self,
        value: Any,
        *,
        when: Optional[str] = None,
        expect: Optional[int] = None,
        result: Optional[str] = None,
        action: Optional[str] = None,
    ):
        self.value: Any = value
        self.when = m_when.When.from_string(when)
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


class TestFile(TestGenerator):
    def __init__(self, root: str, path: Optional[str] = None) -> None:
        super().__init__(root, path=path)
        self.owners: list[str] = []
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
        self._skipif_reason: Optional[str] = None
        self._xstatus: Optional[FilterNamespace] = None
        self.load()

    def describe(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
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
        rh = rh or ResourceHandler()
        cases: list[TestCase] = self.freeze(
            cpus=rh["test:cpu_count"],
            gpus=rh["test:gpu_count"],
            nodes=rh["test:node_count"],
            on_options=on_options,
            keyword_expr=keyword_expr,
        )
        file.write(f"{len(cases)} test case{'' if len(cases) <= 1 else 's'}:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def freeze(
        self,
        cpus: Optional[list[int]] = None,
        gpus: Optional[list[int]] = None,
        nodes: Optional[list[int]] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timeout: Optional[float] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> list[TestCase]:
        try:
            cases = self._freeze(
                cpus=cpus,
                gpus=gpus,
                nodes=nodes,
                keyword_expr=keyword_expr,
                on_options=on_options,
                timeout=timeout,
                parameter_expr=parameter_expr,
                owners=owners,
                env_mods=env_mods,
            )
            return cases
        except Exception as e:
            if config.get("config:debug"):
                raise
            raise ValueError(f"Failed to freeze {self.file}: {e}") from None

    def _freeze(
        self,
        cpus: Optional[list[int]] = None,
        gpus: Optional[list[int]] = None,
        nodes: Optional[list[int]] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timeout: Optional[float] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> list[TestCase]:
        cores_per_socket = config.get("machine:cores_per_socket")
        sockets_per_node = config.get("machine:sockets_per_node") or 1
        cores_per_node = cores_per_socket * sockets_per_node
        min_cpus, max_cpus = cpus or (0, config.get("machine:cpu_count"))
        min_gpus, max_gpus = gpus or (0, config.get("machine:gpu_count"))
        min_nodes, max_nodes = nodes or (0, config.get("machine:node_count"))
        testcases: list[TestCase] = []
        names = ", ".join(self.names())
        logging.debug(f"Generating test cases for {self} using the following test names: {names}")
        for name in self.names():
            global_mask = self.skipif_reason
            if owners and not owners.intersection(self.owners):
                global_mask = colorize("deselected by @*b{owner expression}")
            enabled, reason = self.enable(testname=name, on_options=on_options)
            if not enabled and global_mask is None:
                global_mask = f"deselected due to {reason}"
                logging.debug(f"{self}::{name} has been disabled")
            cases: list[TestCase] = []
            paramsets = self.paramsets(testname=name, on_options=on_options)
            for parameters in ParameterSet.combine(paramsets) or [{}]:
                local_mask: Optional[str] = global_mask
                keywords = self.keywords(testname=name, parameters=parameters)
                if local_mask is None and keyword_expr is not None:
                    kwds = {kw for kw in keywords}
                    kwds.add(name)
                    kwds.update(parameters.keys())
                    kwds.update({"ready"})
                    match = m_when.when({"keywords": keyword_expr}, keywords=list(kwds))
                    if not match:
                        logging.debug(f"Skipping {self}::{name}")
                        local_mask = colorize("deselected by @*b{keyword expression}")

                np = parameters.get("np") or 1
                if not isinstance(np, int):
                    class_name = np.__class__.__name__
                    raise ValueError(
                        f"{self.name}: expected np={np} to be an int, not {class_name}"
                    )

                nc = int(math.ceil(np / cores_per_node))
                if local_mask is None and nc > max_nodes:
                    s = "deselected due to @*b{requiring more nodes than max node count}"
                    local_mask = colorize(s)

                if local_mask is None and nc < min_nodes:
                    s = "deselected due to @*b{requiring fewer nodes than min node count}"
                    local_mask = colorize(s)

                if local_mask is None and np > max_cpus:
                    s = "deselected due to @*b{requiring more cpus than max cpu count}"
                    local_mask = colorize(s)

                if local_mask is None and np < min_cpus:
                    s = "deselected due to @*b{requiring fewer cpus than min cpu count}"
                    local_mask = colorize(s)

                for key in ("ngpu", "ndevice"):
                    # ndevice provides backward compatibility with vvtest
                    if key not in parameters:
                        continue
                    nd = parameters[key]
                    if not isinstance(nd, int) and nd is not None:
                        class_name = nd.__class__.__name__
                        raise ValueError(
                            f"{self.name}: expected {key}={nd} " f"to be an int, not {class_name}"
                        )
                    if local_mask is None and nd and nd > max_gpus:
                        s = "deselected due to @*b{requiring more gpus than max gpu count}"
                        local_mask = colorize(s)
                    if local_mask is None and nd and nd < min_gpus:
                        s = "deselected due to @*b{requiring fewer gpus than min gpu count}"
                        local_mask = colorize(s)
                    break

                if local_mask is None and ("TDD" in keywords or "tdd" in keywords):
                    local_mask = colorize("deselected due to @*b{TDD keyword}")
                if local_mask is None and parameter_expr:
                    match = m_when.when(f"parameters={parameter_expr!r}", parameters=parameters)
                    if not match:
                        local_mask = colorize("deselected due to @*b{parameter expression}")
                attributes = self.attributes(
                    testname=name, on_options=on_options, parameters=parameters
                )

                case = TestCase(
                    self.root,
                    self.path,
                    family=name,
                    keywords=keywords,
                    parameters=parameters,
                    timeout=timeout or self.timeout(testname=name, parameters=parameters),
                    baseline=self.baseline(testname=name, parameters=parameters),
                    sources=self.sources(testname=name, parameters=parameters),
                    xstatus=self.xstatus(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                )
                case.launcher = sys.executable
                if env_mods:
                    case.add_default_env(**env_mods)
                if local_mask is not None:
                    case.mask = local_mask
                elif timeout is not None and timeout > 0 and case.runtime > timeout:
                    case.mask = "runtime exceeds time limit"
                for attr, value in attributes.items():
                    case.set_attribute(attr, value)

                dependencies = self.depends_on(testname=name, parameters=parameters)
                if dependencies:
                    case.add_dependency(*dependencies)

                cases.append(case)

            analyze = self.analyze(testname=name, on_options=on_options)
            if analyze:
                # add previous cases as dependencies
                mask_analyze_case: Optional[str] = None
                if any(case.mask for case in cases):
                    mask_analyze_case = colorize("deselected due to @*b{skipped dependencies}")
                parent = TestMultiCase(
                    self.root,
                    self.path,
                    paramsets=paramsets,
                    flag=analyze,
                    family=name,
                    keywords=self.keywords(testname=name),
                    timeout=timeout or self.timeout(testname=name),
                    baseline=self.baseline(testname=name),
                    sources=self.sources(testname=name),
                    xstatus=self.xstatus(testname=name, on_options=on_options),
                )
                parent.launcher = sys.executable
                if mask_analyze_case is not None:
                    parent.mask = mask_analyze_case
                if env_mods:
                    parent.add_default_env(**env_mods)
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
    def skipif_reason(self) -> Optional[str]:
        return self._skipif_reason

    @skipif_reason.setter
    def skipif_reason(self, arg: str) -> None:
        self._skipif_reason = arg

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

    def xstatus(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> int:
        if self._xstatus is not None:
            result = self._xstatus.when.evaluate(
                testname=testname, parameters=parameters, on_options=on_options
            )
            if result.value:
                return self._xstatus.value
        return 0

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
    ) -> Union[float, None]:
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
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
    ) -> tuple[bool, Union[str, None]]:
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
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[Union[str, tuple[str, str]]]:
        baseline: list[Union[str, tuple[str, str]]] = []
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
                files = glob.glob(os.path.join(dirname, src))
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

    def m_xfail(self, *, code: int = -1, when: Optional[str] = None) -> None:
        ns = FilterNamespace(code, when=when)
        self._xstatus = ns

    def m_xdiff(self, *, when: Optional[str] = None) -> None:
        ns = FilterNamespace(diff_exit_status, when=when)
        self._xstatus = ns

    def m_owners(self, *args: str) -> None:
        self.owners.extend(args)

    def m_depends_on(
        self,
        arg: str,
        when: Optional[str] = None,
        result: Optional[str] = None,
        expect: Optional[int] = None,
    ) -> None:
        ns = FilterNamespace(arg, when=when, result=result, expect=expect)
        self._depends_on.append(ns)

    def m_preload(self, arg: str, source: bool = False, when: Optional[str] = None) -> None:
        ns = FilterNamespace(arg, action="source" if source else None, when=when)
        self._preload.append(ns)

    def m_parameterize(
        self,
        argnames: Union[str, Sequence[str]],
        argvalues: list[Union[Sequence[Any], Any]],
        when: Optional[str] = None,
        type: Optional[enums.enums] = None,
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
            pset = ParameterSet.random_parameter_space(argnames, argvalues, file=self.file)
        else:
            pset = ParameterSet.list_parameter_space(
                argnames,
                argvalues,
                file=self.file,
            )
        for row in pset:
            for key, value in row:
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

    def m_set_attribute(self, when: Optional[str] = None, **kwargs: Any) -> None:
        ns = FilterNamespace(kwargs, when=when)
        self._attributes.append(ns)

    def add_sources(
        self,
        action: str,
        *files: str,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
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
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
    ) -> None:
        self.add_sources("copy", *files, src=src, dst=dst, when=when)

    def m_link(
        self,
        *files: str,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
    ) -> None:
        self.add_sources("link", *files, src=src, dst=dst, when=when)

    def m_sources(
        self,
        *files: str,
        when: Optional[str] = None,
    ) -> None:
        self.add_sources("sources", *files, when=when)

    def m_analyze(
        self,
        *,
        flag: Optional[str] = None,
        script: Optional[str] = None,
        when: Optional[str] = None,
    ) -> None:
        if flag is not None and script is not None:
            raise ValueError(
                "TestFile.analyze: 'script' and 'flag' keyword arguments are mutually exclusive"
            )
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
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
        flag: Optional[str] = None,
    ) -> None:
        ns: FilterNamespace
        if (src is not None) or (dst is not None):
            if src is None:
                raise TypeError("TestFile.baseline: missing required positional argument: `src`")
            if dst is None:
                raise TypeError("TestFile.baseline: missing required positional argument: `dst`")
            if flag is not None:
                raise ValueError(
                    "TestFile.baseline: 'src/dst' and 'flag' keyword arguments are mutually exclusive"
                )
            ns = FilterNamespace((src, dst), when=when)
        elif flag is not None:
            ns = FilterNamespace(flag, when=when)
        else:
            raise ValueError("TestFile.baseline: missing required argument 'src'/'dst' or 'flag'")
        self._baseline.append(ns)

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

    def f_analyze(
        self,
        *,
        when: Optional[str] = None,
        flag: Optional[str] = None,
        script: Optional[str] = None,
    ):
        self.m_analyze(when=when, flag=flag, script=script)

    def f_copy(
        self,
        *args: str,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
    ):
        self.m_copy(*args, src=src, dst=dst, when=when)

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

    def f_cpus(self, *values: int, when: Optional[str] = None) -> None:
        self.m_parameterize("np", list(values), when=when)

    def f_processors(self, *values: int, when: Optional[str] = None) -> None:
        self.m_parameterize("np", list(values), when=when)

    def f_nodes(self, *values: int, when: Optional[str] = None) -> None:
        self.m_parameterize("nnode", list(values), when=when)

    def f_enable(self, *args: bool, when: Optional[str] = None):
        arg = True if not args else args[0]
        self.m_enable(arg, when=when)

    def f_keywords(self, *args: str, when: Optional[str] = None) -> None:
        self.m_keywords(*args, when=when)

    def f_link(
        self,
        *args: str,
        src: Optional[str] = None,
        dst: Optional[str] = None,
        when: Optional[str] = None,
    ):
        self.m_link(*args, src=src, dst=dst, when=when)

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

    def f_baseline(
        self,
        arg1: Optional[str] = None,
        arg2: Optional[str] = None,
        when: Optional[str] = None,
        flag: Optional[str] = None,
    ) -> None:
        self.m_baseline(arg1, arg2, when=when, flag=flag)
