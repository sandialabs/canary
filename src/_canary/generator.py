# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import errno
import fnmatch
import hashlib
import importlib
import os
import sys
from abc import ABC
from abc import abstractmethod
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Sequence

from .error import diff_exit_status
from .paramset import ParameterSet
from .testspec import Artifact
from .testspec import Asset
from .testspec import DependencyPatterns
from .testspec import Mask
from .testspec import UnresolvedSpec
from .util import logging
from .util import reducer
from .util.field import Field
from .util.reducer import Reducer
from .util.reducer import unique
from .util.string import stringify
from .util.time import time_in_seconds

try:
    from typing import Self  # type: ignore
except ImportError:
    from typing_extensions import Self

from schema import Schema
from schema import Type

from .util import json_helper as json

if TYPE_CHECKING:
    from .testspec import ResolvedSpec
    from .testspec import UnresolvedSpec


WhenType = str | dict[str, str]


def flatten_unique(xss: list[list[str]]) -> list[str]:
    return unique(reducer.concat(xss))


class AbstractTestGenerator(ABC):
    """The AbstractTestCaseGenerator is an abstract object representing a test file that
    can generate test cases

    Args:
      root: The base test directory, or file path if ``path`` is not given
      path: The file path, relative to root

    To create a test generator, simply subclass :class:`~AbstractTestGenerator` and register the
    containing file as an ``canary`` plugin.  The subclass will be added to the command registry
    and added to the set of available test generators.

    All ``canary`` builtin generators are implemented as plugins.

    Examples:

    .. code-block:: python

       from typing import Optional

       import canary

       class MyGenerator(canary.AbstractTestGenerator):
           file_patterns = ("*.suffix",)

           def describe(self, on_options: list[str] | None = None) -> str:
               ...

           def lock(self, on_options: list[str] | None = None) -> list[canary.UnresolvedTestSpec]:
               ...

    """

    file_patterns: ClassVar[tuple[str, ...]] = ()

    def __init__(self, root: str, path: str | None = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = os.path.abspath(root)
        self.path = path
        self.file = os.path.join(self.root, self.path)
        if not os.path.exists(self.file):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = os.path.splitext(os.path.basename(self.path))[0]

        sha = hashlib.sha256()
        with open(self.file, "rb") as fh:
            data = fh.read()
            sha.update(data)
        self.sha256: str = sha.hexdigest()
        self.id: str = hashlib.sha256(self.file.encode("utf-8")).hexdigest()[:20]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(file={self.file!r})"

    @classmethod
    def factory(cls, root: str, path: str | None = None) -> Self | None:
        f = root if path is None else path
        if cls.matches(f):
            return cls(root, path=path)
        return None

    @classmethod
    def matches(cls, path: str) -> str | None:
        """Is the file at ``path`` a test file?"""
        name = os.path.basename(path)
        for pattern in cls.file_patterns:
            if fnmatch.fnmatchcase(name, pattern):
                return pattern
        return None

    def describe(self, on_options: list[str] | None = None) -> str:
        """Return a description of the test"""
        return repr(self)

    @abstractmethod
    def lock(
        self, on_options: list[str] | None = None
    ) -> Sequence["UnresolvedSpec | ResolvedSpec"]:
        """Expand parameters and instantiate concrete test cases

        Args:
          on_options: User specified options used to filter tests.  Test cases not matching
            ``on_options`` should be masked.

        Notes:

          For further discussion on filtering tests see :ref:`usage-filter`.

        """

    def asdict(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        state["root"] = self.root
        state["path"] = self.path
        state["mtime"] = os.path.getmtime(self.file)
        return state

    @staticmethod
    def validate(data) -> Any:
        schema = Schema({"module": str, "classname": str, "params": {str: object}})
        return schema.validate(data)

    @staticmethod
    def reconstruct(serialized: str) -> "AbstractTestGenerator":
        meta = json.loads(serialized)
        AbstractTestGenerator.validate(meta)
        module = importlib.import_module(meta["module"])
        cls: Type[AbstractTestGenerator] = getattr(module, meta["classname"])
        params = meta["params"]
        generator = cls(params["root"], params["path"])
        return generator

    def serialize(self) -> str:
        meta = {
            "module": self.__class__.__module__,
            "classname": self.__class__.__name__,
            "params": self.asdict(),
        }
        return json.dumps_min(meta)

    @staticmethod
    def create(root: str, path: str | None = None) -> "AbstractTestGenerator":
        from . import config

        if generator := config.pluginmanager.hook.canary_testcase_generator(root=root, path=path):
            return generator
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"{f} is not a test generator")

    def info(self) -> dict[str, Any]:
        return {}


@dataclasses.dataclass(frozen=True, slots=True)
class ModuleSpec:
    name: str
    use: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class SourceSpec:
    action: Literal["copy", "link", "sources"]
    src: str
    dst: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class BaselineSpec:
    src: str | None = None
    dst: str | None = None
    flag: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class AnalyzeSpec:
    flag: str | None = None
    script: str | None = None
    requires: str = "success"


@dataclasses.dataclass(frozen=True, slots=True)
class XstatusSpec:
    code: int = 0


class TestGenerator(AbstractTestGenerator):
    file_patterns: ClassVar[tuple[str, ...]] = ()

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)

        self.families: Field[str, list[str]] = Field(reducer=reducer.IDENTITY)
        self.parameter_sets: Field[ParameterSet, list[ParameterSet]] = Field(
            reducer=reducer.IDENTITY
        )
        self.keywords: Field[list[str], list[str]] = Field(
            reducer=Reducer("flatten_unique", flatten_unique)
        )
        self.timeout: Field[float, float | None] = Field.make(reducer.LAST)
        self.modules: Field[ModuleSpec, list[ModuleSpec]] = Field(reducer=reducer.IDENTITY)
        self.rcfiles: Field[str, list[str]] = Field(reducer=reducer.IDENTITY)
        self.artifacts: Field[Artifact, list[Artifact]] = Field(reducer=reducer.IDENTITY)
        self.sources: Field[SourceSpec, list[SourceSpec]] = Field(reducer=reducer.IDENTITY)
        self.baseline: Field[BaselineSpec, list[BaselineSpec]] = Field(reducer=reducer.IDENTITY)
        self.exclusive: Field[bool, bool] = Field(reducer=reducer.ANY)
        self.depends_on: Field[DependencyPatterns, list[DependencyPatterns]] = Field(
            reducer=reducer.IDENTITY
        )
        self.attributes: Field[dict[str, Any], dict[str, Any]] = Field(reducer=reducer.MERGE_DICTS)
        self.analyze: Field[AnalyzeSpec, AnalyzeSpec | None] = Field.make(reducer.LAST)
        self.preload: Field[str, str | None] = Field.make(reducer.LAST)
        self.enable: Field[bool, list[bool]] = Field(reducer=reducer.IDENTITY)
        self.skip_reason: Field[str, str | None] = Field.make(reducer.LAST)
        self.xstatus: Field[XstatusSpec, XstatusSpec | None] = Field.make(reducer.LAST)

        self.filter_warnings: bool = False
        self.owners: list[str] = []

        self.command: list[str] = [sys.executable, os.path.basename(self.path)]

    # ----------------------------- add_* API -----------------------------

    def add_family(self, name: str, when: WhenType | None = None) -> None:
        self.families.add(name, when=when)

    def add_owner(self, *names: str) -> None:
        self.owners.extend(names)

    def add_keywords(self, *words: str, when: WhenType | None = None) -> None:
        self.keywords.add(list(words), when=when)

    def add_timeout(self, value: str | float | int, when: WhenType | None = None) -> None:
        self.timeout.add(float(time_in_seconds(value)), when=when)

    def add_parameter_set(self, pset: ParameterSet, when: WhenType | None = None) -> None:
        self.parameter_sets.add(pset, when=when)

    def add_module(self, name: str, use: str | None = None, when: WhenType | None = None) -> None:
        self.modules.add(ModuleSpec(name=name, use=use), when=when)

    def add_rcfile(self, name: str, when: WhenType | None = None) -> None:
        self.rcfiles.add(name, when=when)

    def add_artifact(
        self,
        pattern: str,
        upon: Literal["always", "never", "on_failure", "on_success"] = "always",
        when: WhenType | None = None,
    ) -> None:
        self.artifacts.add(Artifact(pattern=pattern, when=upon), when=when)

    def add_source(
        self,
        action: Literal["copy", "link", "sources"],
        *files: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        if src is not None:
            self.sources.add(SourceSpec(action=action, src=src, dst=dst), when=when)
            return
        for f in files:
            self.sources.add(SourceSpec(action=action, src=f, dst=None), when=when)

    def add_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        flag: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        self.baseline.add(BaselineSpec(src=src, dst=dst, flag=flag), when=when)

    def set_exclusive(self, when: WhenType | None = None) -> None:
        self.exclusive.add(True, when=when)

    def add_dependency(
        self,
        pattern: str,
        expects: int | str | None = None,
        result_match: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        dep = DependencyPatterns(
            pattern=pattern, expects=expects or "+", result_match=result_match or "success"
        )
        self.depends_on.add(dep, when=when)

    def set_attributes(self, when: WhenType | None = None, **attrs: Any) -> None:
        self.attributes.add(dict(attrs), when=when)

    def set_preload(self, arg: str, when: WhenType | None = None) -> None:
        self.preload.add(arg, when=when)

    def set_enable(self, value: bool, when: WhenType | None = None) -> None:
        self.enable.add(bool(value), when=when)

    def set_skipif(self, skip: bool, reason: str) -> None:
        if skip:
            self.skip_reason.add(reason, when=None)

    def set_filter_warnings(self, value: bool) -> None:
        if value:
            self.filter_warnings = True

    def set_analyze(
        self,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
        requires: str = "success",
    ) -> None:
        self.analyze.add(AnalyzeSpec(flag=flag, script=script, requires=requires), when=when)

    def set_xfail(self, when: WhenType | None = None, code: int = -1) -> None:
        self.xstatus.add(XstatusSpec(code=code), when=when)

    def set_xdiff(self, when: WhenType | None = None) -> None:
        self.xstatus.add(XstatusSpec(code=diff_exit_status), when=when)

    # ----------------------------- getters -----------------------------

    def get_families(self, on_options: list[str] | None = None) -> list[str]:
        names = self.families.eval(on_options=on_options)
        return names or [self.name]

    def get_parameters(
        self, family: str, on_options: list[str] | None = None
    ) -> list[dict[str, Any]]:
        psets = self.parameter_sets.eval(family=family, on_options=on_options)
        return ParameterSet.combine(psets)

    def get_keywords(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[str]:
        return self.keywords.eval(family=family, parameters=parameters, on_options=on_options)

    def get_timeout(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> float | None:
        return self.timeout.eval(family=family, parameters=parameters, on_options=on_options)

    def get_modules(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[ModuleSpec]:
        return self.modules.eval(family=family, parameters=parameters, on_options=on_options)

    def get_rcfiles(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[str]:
        return self.rcfiles.eval(family=family, parameters=parameters, on_options=on_options)

    def get_artifacts(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[Artifact]:
        return self.artifacts.eval(family=family, parameters=parameters, on_options=on_options)

    def get_sources(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[SourceSpec]:
        return self.sources.eval(family=family, parameters=parameters, on_options=on_options)

    def get_baseline(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[BaselineSpec]:
        return self.baseline.eval(family=family, parameters=parameters, on_options=on_options)

    def get_exclusive(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> bool:
        return self.exclusive.eval(family=family, parameters=parameters, on_options=on_options)

    def get_dependencies(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[DependencyPatterns]:
        return self.depends_on.eval(family=family, parameters=parameters, on_options=on_options)

    def get_attributes(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.attributes.eval(family=family, parameters=parameters, on_options=on_options)

    def get_preload(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> str | None:
        return self.preload.eval(family=family, parameters=parameters, on_options=on_options)

    def get_enable(self, family=None, parameters=None, on_options=None) -> tuple[bool, str | None]:
        for c in self.enable.items:
            result = c.when.evaluate(testname=family, on_options=on_options, parameters=parameters)
            if c.value is True and not result.value:
                return False, result.reason
            if c.value is False and result.value:
                return False, result.reason or "[bold]enable=False[/]"
        return True, None

    def get_skip_reason(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> str | None:
        return self.skip_reason.eval(family=family, parameters=parameters, on_options=on_options)

    def get_xstatus(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> int:
        xs = self.xstatus.eval(family=family, parameters=parameters, on_options=on_options)
        return xs.code if xs is not None else 0

    def get_analyze(
        self, family: str | None = None, on_options: list[str] | None = None
    ) -> AnalyzeSpec | None:
        return self.analyze.eval(family=family, parameters=None, on_options=on_options)

    # ----------------------------- substitution helpers -----------------------------

    def safe_substitute(self, text: str, **kwds: Any) -> str:
        if "$" in text:
            return Template(text).safe_substitute(**kwds)
        return text.format(**kwds)

    def _sub_kwds(self, family: str | None, parameters: dict[str, Any] | None) -> dict[str, Any]:
        kw: dict[str, Any] = {}
        if parameters:
            kw.update({k: stringify(v) for k, v in parameters.items()})
        if family:
            kw["name"] = family
        for k in list(kw.keys()):
            kw[k.upper()] = kw[k]
        return kw

    # ----------------------------- AbstractTestGenerator API -----------------------------

    def lock(
        self, on_options: list[str] | None = None
    ) -> Sequence["UnresolvedSpec | ResolvedSpec"]:
        if self.filter_warnings:
            with logging.suppress_stream_below(logging.ERROR):
                return self._lock(on_options=on_options)
        return self._lock(on_options=on_options)

    def _lock(self, on_options: list[str] | None = None) -> list[UnresolvedSpec]:
        drafts: list[UnresolvedSpec] = []
        families = self.get_families(on_options=on_options)

        for family in families:
            param_dicts = self.get_parameters(family, on_options=on_options)
            if not param_dicts:
                param_dicts = [{}]

            test_mask: str | None = None
            my_drafts: list[UnresolvedSpec] = []
            dependencies: list[str | DependencyPatterns] = []

            for parameters in param_dicts:
                test_mask = self.get_skip_reason(family, parameters, on_options=on_options)

                keywords = self.get_keywords(family, parameters, on_options=on_options)
                modules = self.get_modules(family, parameters, on_options=on_options)
                timeout = self.get_timeout(family, parameters, on_options=on_options)
                preload = self.get_preload(family, parameters, on_options=on_options)
                xstatus = self.get_xstatus(family, parameters, on_options=on_options)
                exclusive = self.get_exclusive(family, parameters, on_options=on_options)
                rcfiles = self.get_rcfiles(family, parameters, on_options=on_options)
                artifacts = self.get_artifacts(family, parameters, on_options=on_options)
                attributes = self.get_attributes(family, parameters, on_options=on_options)
                baseline_specs = self.get_baseline(family, parameters, on_options=on_options)
                src_specs = self.get_sources(family, parameters, on_options=on_options)
                deps = self.get_dependencies(family, parameters, on_options=on_options)

                kw = self._sub_kwds(family, parameters)

                src: str | None
                dst: str | None
                baseline: list[str | tuple[str, str]] = []
                for b in baseline_specs:
                    if b.flag:
                        baseline.append(b.flag)
                    else:
                        if b.src is None:
                            continue
                        if b.dst is None:
                            continue
                        src = self.safe_substitute(b.src, **kw)
                        dst = self.safe_substitute(b.dst, **kw)
                        baseline.append((src, dst))

                file_resources: dict[
                    Literal["copy", "link", "none"], list[tuple[str, str | None]]
                ] = {}
                for s in src_specs:
                    src = self.safe_substitute(s.src, **kw)
                    dst = self.safe_substitute(s.dst, **kw) if s.dst is not None else None
                    action: Literal["copy", "link", "none"]
                    if s.action == "sources":
                        action = "none"
                    else:
                        action = s.action
                    file_resources.setdefault(action, []).append((src, dst))

                dependencies.clear()
                for dep in deps:
                    dependencies.append(
                        DependencyPatterns(
                            pattern=self.safe_substitute(dep.pattern, **kw),
                            expects=dep.expects,
                            result_match=dep.result_match,
                        )
                    )

                resolved_artifacts: list[Artifact] = []
                for a in artifacts:
                    resolved_artifacts.append(
                        Artifact(pattern=self.safe_substitute(a.pattern, **kw), when=a.when)
                    )

                draft = UnresolvedSpec(
                    file_root=Path(self.root),
                    file_path=Path(self.path),
                    family=family,
                    keywords=keywords,
                    parameters=parameters,
                    modules=[m.name for m in modules],
                    owners=self.owners,
                    timeout=timeout or -1.0,
                    baseline=baseline,
                    file_resources=file_resources,
                    xstatus=xstatus,
                    preload=preload,
                    rcfiles=rcfiles,
                    artifacts=resolved_artifacts,
                    exclusive=exclusive,
                    dependencies=dependencies,
                    command=list(self.command),
                )

                enabled, reason = self.get_enable(family, parameters, on_options=on_options)
                if test_mask is None and enabled is False:
                    test_mask = reason

                if test_mask is not None:
                    draft.mask = Mask.masked(test_mask)

                if any(m.use is not None for m in modules):
                    mp = [x.strip() for x in os.getenv("MODULEPATH", "").split(":") if x.strip()]
                    for m in modules:
                        if m.use:
                            mp.insert(0, m.use)
                    draft.environment["MODULEPATH"] = ":".join(mp)

                for k, v in attributes.items():
                    draft.attributes[k] = v

                my_drafts.append(draft)

            analyze = self.get_analyze(family, on_options=on_options)
            if analyze is not None:
                psets = self.parameter_sets.eval(family=family, on_options=on_options)
                if not any(psets):
                    raise ValueError(
                        "Generation of composite base case requires at least one parameter"
                    )

                modules = self.get_modules(family, parameters=None, on_options=on_options)
                dependencies.clear()
                for d in my_drafts:
                    dependencies.append(
                        DependencyPatterns(pattern=d.id, expects=1, result_match=analyze.requires)
                    )

                pset_meta = []
                for ps in psets:
                    pset_meta.append({"keys": ps.keys, "values": ps.values})

                parent = UnresolvedSpec(
                    file_root=Path(self.root),
                    file_path=Path(self.path),
                    family=family,
                    keywords=self.get_keywords(family, parameters=None, on_options=on_options),
                    timeout=self.get_timeout(family, parameters=None, on_options=on_options)
                    or -1.0,
                    baseline=[],
                    file_resources={},
                    xstatus=self.get_xstatus(family, parameters=None, on_options=on_options),
                    preload=self.get_preload(family, parameters=None, on_options=on_options),
                    modules=[m.name for m in modules],
                    rcfiles=self.get_rcfiles(family, parameters=None, on_options=on_options),
                    owners=self.owners,
                    artifacts=self.get_artifacts(family, parameters=None, on_options=on_options),
                    exclusive=self.get_exclusive(family, parameters=None, on_options=on_options),
                    attributes={"multicase": True, "paramsets": pset_meta},
                    dependencies=dependencies,
                )

                if analyze.flag:
                    parent.command = [sys.executable, os.path.basename(self.path), analyze.flag]
                elif analyze.script:
                    script = analyze.script
                    if os.path.exists(script):
                        f = Path(script).absolute()
                    else:
                        f = Path(os.path.join(self.root, os.path.dirname(self.path), script))
                    if not any(
                        a.action in ("link", "copy") and a.src.name == f.name for a in parent.assets
                    ):
                        parent.assets.append(Asset(f, f.name, action="link"))
                    parent.command = [f.as_posix()]
                else:
                    parent.command = [sys.executable, os.path.basename(self.path)]

                if any(m.use is not None for m in modules):
                    mp = [x.strip() for x in os.getenv("MODULEPATH", "").split(":") if x.strip()]
                    for m in modules:
                        if m.use:
                            mp.insert(0, m.use)
                    parent.environment["MODULEPATH"] = ":".join(mp)

                enabled, reason = self.get_enable(family, parameters=None, on_options=on_options)
                if test_mask is None and enabled is False:
                    test_mask = reason

                if test_mask is not None:
                    parent.mask = Mask.masked(test_mask)

                my_drafts.append(parent)

            drafts.extend(my_drafts)

        return drafts
