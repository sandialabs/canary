# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import io
import os
import warnings
from pathlib import Path
from string import Template
from types import ModuleType
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Sequence
from typing import cast

from ... import config
from ... import enums
from ... import when as m_when
from ...error import diff_exit_status
from ...generator import AbstractTestGenerator
from ...hookspec import hookimpl
from ...launcher import Launcher
from ...launcher import PythonFileLauncher
from ...launcher import PythonRunpyLauncher
from ...launcher import SubprocessLauncher
from ...paramset import ParameterSet
from ...testcase import TestCase
from ...testspec import Mask
from ...third_party.monkeypatch import monkeypatch
from ...util import graph
from ...util import logging
from ...util.string import pluralize
from ...util.string import stringify
from ...util.time import time_in_seconds

if TYPE_CHECKING:
    from ...testspec import DependencyPatterns
    from ...testspec import UnresolvedSpec


WhenType = str | dict[str, str]


logger = logging.get_logger(__name__)


class FilterNamespace:
    def __init__(
        self,
        value: Any,
        *,
        when: WhenType | None = None,
        expect: int | str | None = None,
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

    def __repr__(self) -> str:
        attrs = ", ".join([f"{key}={value}" for key, value in vars(self).items()])
        return f"FilterNamespace({attrs})"

    def enabled(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        result = self.when.evaluate(testname=testname, on_options=on_options, parameters=parameters)
        return result.value


class PYTTestGenerator(AbstractTestGenerator):
    file_patterns: ClassVar[tuple[str, ...]] = ("*.pyt", "canary_*.py")

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
        self._filter_warnings: bool = False
        self._skipif_reason: str | None = None
        self._exclusive: FilterNamespace | None = None
        self._xstatus: FilterNamespace | None = None
        self.load()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path})"

    def describe(self, on_options: list[str] | None = None) -> str:
        from ...generate import resolve

        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Keywords: {', '.join(self.keywords())}\n")
        options = self._option_expressions()
        if options:
            file.write(f"Recognized options: {', '.join(options)}\n")
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
        try:
            specs = self.lock(on_options=on_options)
            resolved = resolve(specs)
            n = len(specs)
            opts = ", ".join(on_options or [])
            file.write(f"{n} test {pluralize('spec', n)} using on_options={opts}:\n")
            try:
                graph.print(resolved, file=file)
            except Exception:  # nosec B110
                pass
        except Exception:
            logger.warning("Unable to generate dependency graph")
        return file.getvalue()

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = super().info()
        info["keywords"] = self.keywords(raw=True)
        info["options"] = self._option_expressions()
        return info

    def _option_expressions(self) -> list[str]:
        """Return a list of option expressions that this generator recognizes"""
        option_expressions: set[str] = set()
        for name, attr in vars(self).items():
            if isinstance(attr, FilterNamespace):
                if attr.when.option_expr:
                    option_expressions.add(attr.when.option_expr)
            elif isinstance(attr, list) and len(attr) and isinstance(attr[0], FilterNamespace):
                for a in attr:
                    if a.when.option_expr:
                        option_expressions.add(a.when.option_expr)
        return list(option_expressions)

    def lock(self, on_options: list[str] | None = None) -> list["UnresolvedSpec"]:
        try:
            specs = self._lock(on_options=on_options)
            return specs
        except Exception as e:
            if config.get("debug"):
                raise
            raise ValueError(f"Failed to lock {self.file}: {e}") from None

    def _lock(self, on_options: list[str] | None = None) -> list["UnresolvedSpec"]:
        from ...testspec import DependencyPatterns
        from ...testspec import UnresolvedSpec

        all_drafts: list["UnresolvedSpec"] = []

        names = ", ".join(self.names())
        logger.debug(f"Generating test specs for {self} using the following test names: {names}")
        for name in self.names():
            skip_reason = self.skipif_reason

            my_drafts: list["UnresolvedSpec"] = []
            paramsets = self.paramsets(testname=name, on_options=on_options)
            test_mask: str | None = None
            for parameters in ParameterSet.combine(paramsets) or [{}]:
                test_mask = skip_reason
                keywords = self.keywords(testname=name, parameters=parameters)
                modules = self.modules(testname=name, on_options=on_options, parameters=parameters)
                draft = UnresolvedSpec(
                    file_root=Path(self.root),
                    file_path=Path(self.path),
                    family=name,
                    keywords=keywords,
                    parameters=parameters,
                    modules=[_[0] for _ in modules],
                    owners=self.owners,
                    timeout=self.timeout(
                        testname=name, on_options=on_options, parameters=parameters
                    )
                    or -1.0,
                    baseline=self.baseline(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    file_resources=self.file_resources(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    xstatus=self.xstatus(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    preload=self.preload(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    rcfiles=self.rcfiles(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    artifacts=self.artifacts(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    exclusive=self.exclusive(
                        testname=name, on_options=on_options, parameters=parameters
                    ),
                    dependencies=self.depends_on(
                        testname=name, parameters=parameters, on_options=on_options
                    ),
                )
                enabled, reason = self.enable(
                    testname=name, on_options=on_options, parameters=parameters
                )
                if test_mask is None and not enabled:
                    test_mask = reason
                if test_mask is not None:
                    draft.mask = Mask.masked(test_mask)
                if any([_[1] is not None for _ in modules]):
                    mp = [_.strip() for _ in os.getenv("MODULEPATH", "").split(":") if _.split()]
                    for _, use in modules:
                        if use:
                            mp.insert(0, use)
                    draft.environment["MODULEPATH"] = ":".join(mp)
                attributes = self.attributes(
                    testname=name, on_options=on_options, parameters=parameters
                )
                for attr, value in attributes.items():
                    draft.attributes[attr] = value
                my_drafts.append(draft)

            if ns := self.generate_composite_base_case(testname=name, on_options=on_options):
                # add previous cases as dependencies
                if not any(paramsets):
                    raise ValueError(
                        "Generation of composite base case requires at least one parameter"
                    )
                modules = self.modules(testname=name, on_options=on_options)
                dependencies: list[str | DependencyPatterns] = [
                    DependencyPatterns(pattern=d.id, expects=1, result_match="success")
                    for d in my_drafts
                ]
                psets = []
                for paramset in paramsets:
                    psets.append({"keys": paramset.keys, "values": paramset.values})
                parent = UnresolvedSpec(
                    file_root=Path(self.root),
                    file_path=Path(self.path),
                    family=name,
                    keywords=self.keywords(testname=name),
                    timeout=self.timeout(testname=name, on_options=on_options) or -1.0,
                    baseline=self.baseline(testname=name, on_options=on_options),
                    file_resources=self.file_resources(testname=name, on_options=on_options),
                    xstatus=self.xstatus(testname=name, on_options=on_options),
                    preload=self.preload(testname=name, on_options=on_options),
                    modules=[_[0] for _ in modules],
                    rcfiles=self.rcfiles(testname=name, on_options=on_options),
                    owners=self.owners,
                    artifacts=self.artifacts(testname=name, on_options=on_options),
                    exclusive=self.exclusive(testname=name, on_options=on_options),
                    attributes={"multicase": True, "analyze": ns.value, "paramsets": psets},
                    dependencies=dependencies,
                )
                if test_mask is not None:
                    parent.mask = Mask.masked(test_mask)
                if any([_[1] is not None for _ in modules]):
                    mp = [_.strip() for _ in os.getenv("MODULEPATH", "").split(":") if _.split()]
                    for _, use in modules:
                        if use:
                            mp.insert(0, use)
                    parent.environment["MODULEPATH"] = ":".join(mp)
                my_drafts.append(parent)

            all_drafts.extend(my_drafts)
        return all_drafts

    # -------------------------------------------------------------------------------- #

    @property
    def filter_warnings(self) -> bool:
        return self._filter_warnings

    @filter_warnings.setter
    def filter_warnings(self, arg: bool) -> None:
        self._filter_warnings = arg

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
        raw: bool = False,
    ) -> list[str]:
        keywords: set[str] = set()
        for ns in self._keywords:
            result = ns.when.evaluate(testname=testname, parameters=parameters)
            if raw or result.value:
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
    ) -> FilterNamespace | None:
        for ns in self._generate_composite_base_case:
            result = ns.when.evaluate(testname=testname, on_options=on_options)
            if not result.value:
                continue
            return ns
        return None

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
        parameters: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        for ns in self._enable:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if ns.value is True and not result.value:
                return False, result.reason
            elif ns.value is False and result.value:
                reason = result.reason or "[bold]enable=False[/]"
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

    def file_resources(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]]:
        kwds = dict(parameters) if parameters else {}
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        sources: dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]] = {}
        dirname = os.path.join(self.root, os.path.dirname(self.path))
        src_not_found: dict[str, set[str]] = {}
        for ns in self._sources:
            assert isinstance(ns.action, str)
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            src, dst = ns.value
            src = self.safe_substitute(src, **kwds)
            src = src if os.path.isabs(src) else os.path.join(dirname, src)

            # Find paths to sources
            found = glob.glob(src)
            if not found:
                # Source does not exist, we'll warn for now and raise an error lazily when
                # the file is needed
                src_not_found.setdefault(ns.action, set()).add(src)
                fd = None if dst is None else self.safe_substitute(dst, **kwds)
                action = cast(Literal["copy", "link", "none"], ns.action)
                sources.setdefault(action, []).append((os.path.relpath(src, dirname), fd))
            elif dst is not None:
                # Explicitly request to copy/link source to a new destination
                if len(found) > 1:
                    raise ValueError(
                        f"{self}: {ns.action} {src} -> {dst}: cannot {ns.action} "
                        "multiple sources to a single destination"
                    )
                dst = self.safe_substitute(dst, **kwds)
                action = cast(Literal["copy", "link", "none"], ns.action)
                sources.setdefault(action, []).append((os.path.relpath(found[0], dirname), dst))
            else:
                for src in found:
                    sources.setdefault(ns.action, []).append((os.path.relpath(src, dirname), None))  # type: ignore

        if src_not_found:
            msg = io.StringIO()
            msg.write(f"{self}: the following support files were not found:\n")
            for copy_action in src_not_found:
                for src in sorted(src_not_found[copy_action]):
                    msg.write(f"...  {src} (action: {copy_action})\n")
            logger.warning(msg.getvalue().strip())

        return sources

    def depends_on(
        self,
        testname: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> list["str | DependencyPatterns"]:
        from ...testspec import DependencyPatterns

        kwds: dict[str, Any] = {}
        if parameters:
            kwds.update({k: stringify(v) for k, v in parameters.items()})
        if testname:
            kwds["name"] = testname
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        dependencies: list["str | DependencyPatterns"] = []
        for ns in self._depends_on:
            result = ns.when.evaluate(
                testname=testname, on_options=on_options, parameters=parameters
            )
            if not result.value:
                continue
            dep = DependencyPatterns(
                pattern=ns.value, result_match=ns.result or "success", expects=ns.expect or "+"
            )
            dependencies.append(dep)
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
        arg: str | list[str],
        when: WhenType | None = None,
        result: str | None = None,
        expect: int | str | None = None,
    ) -> None:
        if isinstance(expect, str) and expect not in "?+*":
            raise ValueError(
                f"{self.path}: depends_on: expect: expected one of '?+*', got {expect!r}"
            )
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
        random_seed: float = 1234.0,
    ) -> None:
        type = type or enums.list_parameter_space
        if not isinstance(type, enums.enums):
            raise ValueError(
                f"{self.path}: parameterize: type: expected "
                f"canary.enums, got {type.__class__.__name__}"
            )
        if type is enums.centered_parameter_space:
            pset = ParameterSet.centered_parameter_space(argnames, argvalues, file=self.file)
        elif type is enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                argnames, argvalues, samples=samples, random_seed=random_seed, file=self.file
            )
        else:
            pset = ParameterSet.list_parameter_space(
                argnames,
                argvalues,
                file=self.file,
            )
        for row in pset:
            for i, (key, value) in enumerate(row):
                if key in ("cpus", "gpus", "nodes", "np", "ndevice", "nnode"):
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
        def check_existence(path):
            if os.path.isabs(path):
                return os.path.exists(path)
            # If not absolute, should be relative to test's directory
            return os.path.exists(os.path.join(self.root, os.path.dirname(self.path), path))

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

    def m_generate_composite_base_case(
        self,
        *,
        flag: str | None = None,
        script: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        if flag is not None and script is not None:
            raise ValueError(
                "PYTTestGenerator.generate_composite_base_case: "
                "'script' and 'flag' keyword arguments are mutually exclusive"
            )
        arg: str | None = None
        if script is not None:
            arg = script
        elif flag is not None:
            arg = flag
        ns = FilterNamespace(arg, when=when)
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

    def m_filter_warnings(self, arg: bool) -> None:
        if arg:
            self.filter_warnings = True

    def m_skipif(self, arg: bool, *, reason: str) -> None:
        if arg:
            self.skipif_reason = reason

    def m_stages(self, *args: str) -> None:
        warnings.warn("stages: function deprecated", category=DeprecationWarning, stacklevel=2)

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
                    "PYTTestGenerator.baseline: missing required positional argument: `src`"
                )
            if dst is None:
                raise TypeError(
                    "PYTTestGenerator.baseline: missing required positional argument: `dst`"
                )
            if flag is not None:
                raise ValueError(
                    "PYTTestGenerator.baseline: 'src/dst' and 'flag' keyword arguments are mutually exclusive"
                )
            ns = FilterNamespace((src, dst), when=when)
        elif flag is not None:
            ns = FilterNamespace(flag, when=when)
        else:
            raise ValueError(
                "PYTTestGenerator.baseline: missing required argument 'src/dst' or 'flag'"
            )
        self._baseline.append(ns)

    def load(self):
        import canary
        from _canary import set_file_scanning

        try:
            # Replace functions in the dummy canary.directives module with
            # instance methods of this test file so that calls to the directives
            # are passed to this test
            m = ModuleType("directives")
            m.__file__ = f"{m.__name__}.py"
            for item in dir(self):
                if item.startswith("f_"):
                    setattr(m, item[2:], getattr(self, item))
            set_file_scanning(True)
            with monkeypatch.context() as mp:
                mp.setattr(canary, "directives", m)
                code = compile(open(self.file).read(), self.file, "exec")
                safe_globals = {"__name__": "__load__", "__file__": self.file}
                try:
                    exec(code, safe_globals)  # nosec B102
                except SystemExit:
                    pass
        finally:
            set_file_scanning(False)

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
        *args: str,
        when: WhenType | None = None,
        expect: int | str | None = None,
        result: str | None = None,
    ):
        self.m_depends_on(list(args), when=when, result=result, expect=expect)

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

    def f_stages(self, *args: str) -> None:
        warnings.warn("stages: function deprecated", category=DeprecationWarning, stacklevel=2)

    def f_artifact(self, file: str, *, when: WhenType | None = None, upon: str = "always") -> None:
        if upon not in ("always", "success", "failure"):
            raise ValueError("upon: invalid value, choose from 'always', 'success', 'failure'")
        self.m_artifact(file, when=when, upon=upon)

    def f_exclusive(self, *, when: WhenType | None = None) -> None:
        self.m_exclusive(when=when)

    def f_set_attribute(self, *, when: WhenType | None = None, **attributes: Any) -> None:
        self.m_set_attribute(when=when, **attributes)

    def f_filter_warnings(self, arg: bool) -> None:
        self.m_filter_warnings(arg)

    def f_skipif(self, arg: bool, *, reason: str) -> None:
        self.m_skipif(arg, reason=reason)

    def f_sources(self, *args: str, when: WhenType | None = None):
        self.m_sources(*args, when=when)

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


@hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(PYTTestGenerator)


@hookimpl
def canary_runtest_launcher(case: TestCase) -> Launcher | None:
    if case.spec.file.suffix in (".pyt", ".py"):
        if script := case.get_attribute("alt_script"):
            return SubprocessLauncher([f"./{script}"])
        if os.getenv("CANARY_USE_RUNPY_LAUNCHER"):
            return PythonRunpyLauncher()
        return PythonFileLauncher()
    return None
