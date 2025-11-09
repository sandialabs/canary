# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import datetime
import fnmatch
import hashlib
import itertools
import json
import math
import os
import re
import shlex
import string
import sys
import time
from contextlib import contextmanager
from functools import cached_property
from graphlib import TopologicalSorter
from pathlib import Path
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Literal
from typing import Protocol

from . import config
from . import when
from .util import filesystem
from .util import logging
from .util.parallel import starmap
from .util.string import stringify

if TYPE_CHECKING:
    from .generator import AbstractTestGenerator
    from .testcase import TestCase as LegacyTestCase

logger = logging.get_logger(__name__)


# FIXME: Major things to address: case.dep_condition_flags()
#        needs to be checked when filtering, as is currently done for case


class PathEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


class Named(Protocol):
    file_root: Path
    file_path: Path
    family: str
    parameters: dict[str, Any]
    rparameters: dict[str, int]

    @cached_property
    def id(self) -> str: ...
    @cached_property
    def file(self) -> Path: ...
    @cached_property
    def name(self) -> str: ...
    @cached_property
    def display_name(self) -> str: ...
    def s_params(self, sep: str = ",") -> str: ...


class SpecCommons:
    def __hash__(self: Named) -> int:
        return hash(self.id)

    @cached_property
    def file(self: Named) -> Path:
        return self.file_root / self.file_path

    @cached_property
    def name(self: Named) -> str:
        name = self.family
        if p := self.s_params(sep="."):
            name = f"{name}.{p}"
        return name

    @cached_property
    def fullname(self: Named) -> str:
        return str(self.file_path / self.name)

    @cached_property
    def display_name(self: Named) -> str:
        name = self.family
        if p := self.s_params():
            name = f"{name}[{p}]"
        return name

    def s_params(self: Named, sep: str = ",") -> str | None:
        if self.parameters:
            parts = [f"{p}={stringify(self.parameters[p])}" for p in self.parameters]
            return sep.join(parts)
        return None

    @cached_property
    def pretty_name(self: Named) -> str:
        if not self.parameters:
            return self.name
        parts: list[str] = []
        colors = itertools.cycle("bmgycr")
        for key in sorted(self.parameters):
            value = stringify(self.parameters[key])
            parts.append("@%s{%s=%s}" % (next(colors), key, value))
        return f"{self.name}[{','.join(parts)}]"

    @property
    def implicit_keywords(self: Named) -> set[str]:
        """Implicit keywords, used for some filtering operations"""
        return {self.id, self.name, self.family, str(self.file)}

    @property
    def implicit_parameters(self: Named) -> dict[str, int | float]:
        parameters: dict[str, int | float] = {}
        for key, value in self.rparameters.items():
            if key not in self.parameters:
                parameters[key] = value
        if "np" not in self.parameters:
            parameters["np"] = parameters["cpus"]
        if "nnode" not in self.parameters:
            parameters["nnode"] = parameters["nodes"]
        if "ndevice" not in self.parameters:
            parameters["ndevice"] = parameters["gpus"]
        if rt := getattr(self, "runtime", None):
            parameters["runtime"] = float(rt)
        return parameters

    def required_resources(self) -> list[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = []
        for name, value in self.rparameters.items():
            if name == "nodes":
                continue
            group.extend([{"type": name, "slots": 1} for _ in range(value)])
        # by default, only one resource group is returned
        return [group]

    def asdict(self) -> dict:
        return dataclasses.asdict(self)

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, cls=PathEncoder, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), cls=PathEncoder, **kwargs)

    def matches(self, arg: str) -> bool:
        if self.id.startswith(arg):
            return True
        if self.display_name == arg:
            return True
        if self.name == arg:
            return True
        return False


@dataclasses.dataclass(frozen=True)
class TestSpec(SpecCommons):
    id: str
    file_root: Path
    file_path: Path
    family: str
    dependencies: list["TestSpec"]
    keywords: list[str]
    parameters: dict[str, Any]
    rparameters: dict[str, int]
    assets: list["Asset"]
    baseline: list[dict]
    artifacts: list[dict[str, str]]
    exclusive: bool
    timeout: float
    xstatus: int
    preload: str | None
    modules: list[str] | None
    rcfiles: list[str] | None
    owners: list[str] | None
    mask: str

    @classmethod
    def from_dict(cls, d: dict, lookup: dict[str, "TestSpec"]) -> "TestSpec":
        d["file_root"] = Path(d.pop("file_root"))
        d["file_path"] = Path(d.pop("file_path"))
        dependencies: list[TestSpec] = []
        for dep in d["dependencies"]:
            dependencies.append(lookup[dep["id"]])
        d["dependencies"] = dependencies
        assets: list[Asset] = []
        for a in d["assets"]:
            assets.append(Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]))
        d["assets"] = assets
        self = TestSpec(**d)  # ty: ignore[missing-argument]
        return self


@dataclasses.dataclass
class ResolvedSpec(SpecCommons):
    id: str
    file_root: Path
    file_path: Path
    family: str
    dependencies: list["ResolvedSpec"]
    keywords: list[str]
    parameters: dict[str, Any]
    rparameters: dict[str, int]
    assets: list["Asset"]
    baseline: list[dict]
    artifacts: list[dict[str, str]]
    exclusive: bool
    timeout: float
    xstatus: int
    preload: str | None
    modules: list[str] | None
    rcfiles: list[str] | None
    owners: list[str] | None
    mask: str = ""

    @classmethod
    def from_dict(cls, d: dict, lookup: dict[str, "ResolvedSpec"]) -> "ResolvedSpec":
        d["file_root"] = Path(d.pop("file_root"))
        d["file_path"] = Path(d.pop("file_path"))
        dependencies: list[ResolvedSpec] = []
        for dep in d["dependencies"]:
            dependencies.append(lookup[dep["id"]])
        d["dependencies"] = dependencies
        assets: list[Asset] = []
        for a in d["assets"]:
            assets.append(Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]))
        d["assets"] = assets
        self = ResolvedSpec(**d)  # ty: ignore[missing-argument]
        return self


@dataclasses.dataclass
class Asset:
    src: Path
    dst: str
    action: Literal["copy", "link", "none"]


@dataclasses.dataclass
class DependencyPatterns:
    """String representation of test dependencies

    Dependency resolution is performed after test case discovery.  The ``DependencyPatterns``
    object holds information needed to perform the resolution.

    Args:
      value: The dependency name or glob pattern.
      expect: For glob patterns, how many dependencies are expected to be found
      result: The test case will run if the dependency exits with this status.  Usually ``success``

    """

    pattern: str
    expects: str | int = "+"
    result_match: str = "success"
    patterns: list[str] = dataclasses.field(default_factory=list, init=False)
    resolves_to: list[str] = dataclasses.field(default_factory=list, init=False)

    def __post_init__(self):
        self.patterns = shlex.split(self.pattern)
        if self.expects is None:
            self.expects = "+"

    def matches(self, spec: "DraftSpec") -> bool:
        names = {
            spec.name,
            spec.family,
            spec.fullname,
            spec.display_name,
            str(spec.file_path),
            str(spec.file_path.parent / spec.display_name),
        }
        for pattern in self.patterns:
            for name in names:
                if name == pattern or fnmatch.fnmatchcase(name, pattern):
                    return True
        return False

    def update(self, *ids: str) -> None:
        self.resolves_to.extend(ids)

    def verify(self) -> list[str]:
        n = len(self.resolves_to)
        errors: list[str] = []
        if self.expects == "+":
            if n < 1:
                errors.append(f"pattern {self.pattern!r} expected at least 1 match, got {n}")
        elif self.expects == "?":
            if n > 1:
                errors.append(f"pattern {self.pattern!r} expected at most 1 match, got {n}")
        elif isinstance(self.expects, int) and self.expects != n:
            errors.append(f"pattern {self.pattern!r} expected {self.expects} match[es], got {n}")
        return errors


@dataclasses.dataclass
class DraftSpec(SpecCommons):
    """Temporary object used to hold test spec properties until a concrete spec can be created
    after dependency resolution"""

    file_root: Path
    file_path: Path
    family: str = ""
    dependencies: list[str | DependencyPatterns] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    file_resources: dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]] = (
        dataclasses.field(default_factory=dict)
    )
    baseline: list[str | tuple[str, str]] = dataclasses.field(default_factory=list)
    artifacts: list[dict[str, str]] = dataclasses.field(default_factory=list)
    exclusive: bool = False
    timeout: float = -1.0
    xstatus: int = 0
    preload: str | None = None
    modules: list[str] | None = None
    rcfiles: list[str] | None = None
    owners: list[str] | None = None
    mask: str | None = None
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)

    # Fields that are generated in __post_init__
    id: str = dataclasses.field(default="", init=False)
    assets: list[Asset] = dataclasses.field(default_factory=list, init=False)
    baseline_actions: list[dict] = dataclasses.field(default_factory=list, init=False)
    dependency_patterns: list[DependencyPatterns] = dataclasses.field(
        default_factory=list, init=False
    )
    rparameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    resolved_dependencies: list["DraftSpec"] = dataclasses.field(default_factory=list, init=False)
    resolved: bool = dataclasses.field(default=False, init=False)

    def __post_init__(self) -> None:
        assert self.file.exists()
        self.family = self.family or self.file.stem
        self.id = self._generate_id()

        # We make sure objects have the right type, in case any were passed in as name=None
        if self.timeout < 0 or self.timeout is None:
            self.timeout = self._default_timeout()
        if self.xstatus is None:
            self.xstatus = 0
        self.keywords = self.keywords or []
        self.file_resources = self.file_resources or []
        self.parameters = self._validate_parameters(self.parameters or {})
        self.assets = self._generate_assets(self.assets or {})
        self.baseline_actions = self._generate_baseline_actions(self.baseline or [])
        self.exclusive = bool(self.exclusive)
        self.dependency_patterns = self._generate_dependency_patterns(self.dependencies or [])

    @classmethod
    def from_dict(cls, d: dict, lookup: dict[str, "DraftSpec"]) -> "DraftSpec":
        """Reconstruct a DraftSpec from the output of asdict"""
        attrs: dict[str, Any] = {}
        attrs["file_root"] = Path(d.pop("file_root"))
        attrs["file_path"] = Path(d.pop("file_path"))
        attrs["family"] = d.pop("family")
        attrs["keywords"] = d.pop("keywords")
        attrs["artifacts"] = d.pop("artifacts")
        attrs["dependencies"] = d.pop("dependencies")
        attrs["exclusive"] = d.pop("exclusive")
        attrs["timeout"] = d.pop("timeout")
        attrs["xstatus"] = d.pop("xstatus")
        attrs["preload"] = d.pop("preload")
        attrs["modules"] = d.pop("modules")
        attrs["rcfiles"] = d.pop("rcfiles")
        attrs["owners"] = d.pop("owners")
        attrs["mask"] = d.pop("mask")
        attrs["attributes"] = d.pop("attributes")
        draft = DraftSpec(**attrs)  # ty: ignore[missing-argument]

        # Reconstruct internal objects
        assets: list[Asset] = []
        for a in d["assets"]:
            assets.append(Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]))
        draft.assets.clear()
        draft.assets.extend(assets)

        draft.parameters.clear()
        draft.parameters.update(d["parameters"])
        draft.baseline = d["baseline"]
        draft.baseline_actions = d["baseline_actions"]
        draft.dependency_patterns = d["dependency_patterns"]
        draft.resolved_dependencies = [lookup[ds["id"]] for ds in d["resolved_dependencies"]]
        draft.resolved = d["resolved"]
        return draft

    def resolve(self, *specs: "DraftSpec") -> None:
        self.resolved_dependencies.clear()
        self.resolved_dependencies.extend(specs)
        errors: list[str] = []
        for dp in self.dependency_patterns:
            if e := dp.verify():
                errors.extend(e)
        if errors:
            raise UnresolvedDependenciesErrors(errors)
        self.resolved = True

    def is_resolved(self) -> bool:
        return self.resolved

    def _generate_assets(
        self, file_resources: dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]]
    ) -> list[Asset]:
        assets: list[Asset] = []
        dirname = self.file.parent
        for action, items in file_resources.items():
            for a, b in items:
                src: Path = Path(a)
                if not src.is_absolute():
                    src = dirname / src
                if not src.exists():
                    logger.debug(f"{self}: {action} resource file {str(src)} not found")
                dst: str = b if b is not None else src.name
                assets.append(Asset(action=action, src=src, dst=dst))
        return assets

    def _default_timeout(self) -> float:
        timeout: float
        if t := config.get("config:timeout:*"):
            timeout = float(t)
        else:
            for keyword in self.keywords:
                if t := config.get(f"config:timeout:{keyword}"):
                    timeout = float(t)
                    break
            else:
                timeout = float(config.get("config:timeout:default"))
        return timeout

    def _generate_baseline_actions(self, items: list[str | tuple[str, str]]) -> list[dict]:
        actions: list[dict] = []
        for item in items:
            if isinstance(item, str):
                # Single item -> this is an executable to run to perform the baseline
                exe: str
                args: list[str] = []
                if os.path.exists(item):
                    exe = item
                else:
                    exe = sys.executable
                    args.extend([self.file.name, item])
                actions.append({"type": "exe", "exe": exe, "args": args})
            else:
                src, dst = item
                actions.append({"type": "copy", "src": src, "dst": dst})
        return actions

    def _validate_parameters(self, data: dict[str, Any]) -> dict[str, Any]:
        """Default parameters used to set up resources required by test case"""
        self.rparameters.clear()
        self.rparameters.update({"cpus": 1, "gpus": 0, "nodes": 1})
        resource_types: set[str] = set(config.pluginmanager.hook.canary_resource_pool_types())
        resource_types.update(("np", "gpus", "nnode"))  # vvtest compatibility
        for key, value in data.items():
            if key in resource_types and not isinstance(value, int):
                raise InvalidTypeError(key, value)
        exclusive_pairs = [("cpus", "np"), ("gpus", "ndevice"), ("nodes", "nnode")]
        for a, b in exclusive_pairs:
            if a in data and b in data:
                raise MutuallyExclusiveParametersError(a, b)
        if {"nodes", "nnode"} & data.keys():
            bad = {"cpus", "gpus", "np", "ndevice"} & data.keys()
            if bad:
                raise MutuallyExclusiveParametersError("nodes", ",".join(bad))
            nodes: int = int(data.get("nodes", data.get("nnode")))
            rpcount = config.pluginmanager.hook.canary_resource_pool_count
            self.rparameters["nodes"] = nodes
            self.rparameters["cpus"] = nodes * rpcount(type="cpu")
            self.rparameters["gpus"] = nodes * rpcount(type="gpu")
        if {"cpus", "np"} & data.keys():
            cpus: int = int(data.get("cpus", data.get("np")))
            self.rparameters["cpus"] = cpus
            cpu_count = config.pluginmanager.hook.canary_resource_pool_count(type="cpu")
            node_count = config.pluginmanager.hook.canary_resource_pool_count(type="node")
            cpus_per_node = math.ceil(cpu_count / node_count)
            if cpus_per_node > 0:
                nodes = max(self.rparameters["nodes"], math.ceil(cpus / cpus_per_node))
                self.rparameters["nodes"] = nodes
        if {"gpus", "ndevice"} & data.keys():
            gpus: int = int(data.get("gpus", data.get("ndevice")))
            self.rparameters["gpus"] = gpus
            gpu_count = config.pluginmanager.hook.canary_resource_pool_count(type="gpu")
            node_count = config.pluginmanager.hook.canary_resource_pool_count(type="node")
            gpus_per_node = math.ceil(gpu_count / node_count)
            if gpus_per_node > 0:
                nodes = max(self.rparameters["nodes"], math.ceil(gpus / gpus_per_node))
                self.rparameters["nodes"] = nodes
        # We have already done validation, now just fill in missing resource types
        resource_types = resource_types - {"nodes", "cpus", "gpus", "nnode", "np", "ndevice"}
        for key, value in data.items():
            if key in resource_types:
                self.rparameters[key] = value
        return data

    def _generate_dependency_patterns(
        self, args: list[str | DependencyPatterns]
    ) -> list[DependencyPatterns]:
        dependency_patterns: list[DependencyPatterns] = []
        for arg in args:
            if isinstance(arg, DependencyPatterns):
                dependency_patterns.append(arg)
            else:
                t = string.Template(arg)
                pattern = t.safe_substitute(**self.parameters)
                dep_pattern = DependencyPatterns(pattern=pattern)
                dependency_patterns.append(dep_pattern)
        return dependency_patterns

    def _generate_id(self) -> str:
        # Hasher is used to build ID
        hasher = hashlib.sha256()
        hasher.update(self.name.encode())
        if self.parameters:
            for p in sorted(self.parameters):
                hasher.update(f"{p}={stringify(self.parameters[p], float_fmt='%.16e')}".encode())
        hasher.update(self.file.read_bytes())
        d = self.file.parent
        while d.parent != d:
            if (d / ".git").exists() or (d / ".repo").exists():
                f = str(os.path.relpath(str(self.file), str(d)))
                hasher.update(f.encode())
                break
            d = d.parent
        else:
            hasher.update(str(self.file_path.parent / self.name).encode())
        return hasher.hexdigest()[:20]


    @classmethod
    def from_legacy_testcase(cls, case: "LegacyTestCase") -> "DraftSpec":
        spec = cls(
            file_root=Path(case.file_root),
            file_path=Path(case.file_path),
            family=case.family,
            keywords=case.keywords,
            parameters=case.parameters,
            baseline=case.baseline,
            exclusive=case.exclusive,
            timeout=case._timeout or -1.0,
            xstatus=case.xstatus,
            preload=case.preload,
            modules=case.modules,
            rcfiles=case.rcfiles,
            owners=case.owners,
            mask=case.mask,
        )
        dependency_patterns: list[DependencyPatterns] = []
        for ud in case.unresolved_dependencies:
            pattern = " ".join(ud.value)
            dp = DependencyPatterns(
                pattern=pattern, expects=ud.expect or "+", result_match=ud.result
            )
            dependency_patterns.append(dp)
        spec.dependency_patterns.clear()
        spec.dependency_patterns.extend(dependency_patterns)
        assets: list[Asset] = []
        for a in case.assets:
            assets.append(Asset(src=Path(a.src), dst=a.dst or Path(a.src).name, action=a.action))  # ty: ignore[invalid-argument-type]
        spec.assets.clear()
        spec.assets.extend(assets)
        if case.artifacts:
            spec.artifacts.clear()
            spec.artifacts.extend(case.artifacts)
        return spec


def resolve(draft_specs: list[DraftSpec]) -> list[ResolvedSpec]:
    errors: dict[str, list[str]] = {}
    for draft in draft_specs:
        matches: list[str] = []
        for dp in draft.dependency_patterns:
            specs = [u for u in draft_specs if u is not draft and dp.matches(u)]
            dp.update(*[u.id for u in specs])
            matches.extend(specs)
        try:
            draft.resolve(*matches)
        except UnresolvedDependenciesErrors as e:
            errors.setdefault(draft.fullname, []).extend(e.errors)
    if errors:
        msg: list[str] = ["Dependency resolution failed:"]
        for name, issues in errors.items():
            msg.append(f"  {name}")
            msg.extend(f"  • {p}" for p in issues)
        raise DependencyResolutionFailed("\n".join(msg))

    map: dict[str, ResolvedSpec] = {}
    graph: dict[str, list[str]] = {}
    for draft in draft_specs:
        if not draft.is_resolved():
            raise ValueError(f"{draft}: unresolved draft!")
        map[draft.id] = draft
        graph[draft.id] = [d.id for d in draft.resolved_dependencies]

    specs: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            dependencies = []
            draft = map[id]
            for dp in draft.resolved_dependencies:
                dependencies.append(specs[dp.id])
            spec = ResolvedSpec(
                id=draft.id,
                file_root=draft.file_root,
                file_path=draft.file_path,
                family=draft.family,
                dependencies=dependencies,
                keywords=draft.keywords,
                parameters=draft.parameters,
                rparameters=draft.rparameters,
                assets=draft.assets,
                baseline=draft.baseline_actions,
                artifacts=draft.artifacts,
                exclusive=draft.exclusive,
                timeout=draft.timeout,
                xstatus=draft.xstatus,
                preload=draft.preload,
                modules=draft.modules,
                rcfiles=draft.rcfiles,
                owners=draft.owners,
                mask=draft.mask,
            )
            specs[id] = spec
        ts.done(*ids)
    return list(specs.values())


def finalize(resolved_specs: list[ResolvedSpec]) -> list[TestSpec]:
    map: dict[str, ResolvedSpec] = {}
    graph: dict[str, list[str]] = {}
    for resolved_spec in resolved_specs:
        map[resolved_spec.id] = resolved_spec
        graph[resolved_spec.id] = [s.id for s in resolved_spec.dependencies]
    specs: dict[str, TestSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            dependencies = []
            resolved = map[id]
            for dep in resolved.dependencies:
                dependencies.append(specs[dep.id])
            spec = TestSpec(
                id=resolved.id,
                file_root=resolved.file_root,
                file_path=resolved.file_path,
                family=resolved.family,
                dependencies=dependencies,
                keywords=resolved.keywords,
                parameters=resolved.parameters,
                rparameters=resolved.rparameters,
                assets=resolved.assets,
                baseline=resolved.baseline,
                artifacts=resolved.artifacts,
                exclusive=resolved.exclusive,
                timeout=resolved.timeout,
                xstatus=resolved.xstatus,
                preload=resolved.preload,
                modules=resolved.modules,
                rcfiles=resolved.rcfiles,
                owners=resolved.owners,
                mask=resolved.mask,
            )
            specs[id] = spec
        ts.done(*ids)
    return list(specs.values())


def apply_masks(
    specs: list[ResolvedSpec],
    *,
    keyword_exprs: list[str] | None = None,
    parameter_expr: str | None = None,
    owners: set[str] | None = None,
    regex: str | None = None,
    ids: list[str] | None = None,
) -> None:
    """Filter test specs (mask test specs that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      ids: Include those tests matching these ids

    """
    msg = "@*{Masking} test specs based on filtering criteria"

    start = time.monotonic()
    logger.log(logging.INFO, msg, extra={"end": "..."})

    rx: re.Pattern | None = None
    if regex is not None:
        logger.warning("Regular expression search can be slow for large test suites")
        rx = re.compile(regex)

    owners = set(owners or [])

    # Get an index of sorted order
    map: dict[str, int] = {d.id: i for i, d in enumerate(specs)}
    graph: dict[int, int] = {map[s.id]: [map[_.id] for _ in s.dependencies] for s in specs}
    ts = TopologicalSorter(graph)
    order = list(ts.static_order())

    try:
        for i in order:
            spec = specs[i]

            if spec.mask:
                continue

            if ids is not None:
                if not any(spec.matches(id) for id in ids):
                    expr = ",".join(ids)
                    spec.mask = "testspec expression @*{%s} did not match" % expr
                continue

            try:
                check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=spec)
            except Exception as e:
                spec.mask = "@*{%s}(%r)" % (e.__class__.__name__, e.args[0])
                continue
            else:
                if not check:
                    spec.mask = check.reason
                    continue

            if owners and not owners.intersection(spec.owners or []):
                spec.mask = "not owned by @*{%r}" % spec.owners
                continue

            if keyword_exprs is not None:
                kwds = set(spec.keywords)
                kwds.update(spec.implicit_keywords)
                kwd_all = contains_any(("__all__", ":all:"), keyword_exprs)
                if not kwd_all:
                    for keyword_expr in keyword_exprs:
                        match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                        if not match:
                            spec.mask = "keyword expression @*{%r} did not match" % keyword_expr
                            break
                    if spec.mask:
                        continue

            if parameter_expr:
                match = when.when(
                    {"parameters": parameter_expr},
                    parameters=spec.parameters | spec.implicit_parameters,
                )
                if not match:
                    spec.mask = "parameter expression @*{%s} did not match" % parameter_expr
                    continue

            if rx is not None:
                if not filesystem.grep(rx, spec.file):
                    for asset in spec.assets:
                        if os.path.isfile(asset.src) and filesystem.grep(rx, asset.src):
                            break
                    else:
                        spec.mask = "@*{re.search(%r) is None} evaluated to @*g{True}" % regex
                        continue

    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - start)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)

    propagate_masks(specs)


def propagate_masks(specs: list[ResolvedSpec]) -> None:
    changed: bool = True
    while changed:
        changed = False
        for spec in specs:
            if spec.mask:
                continue
            if any(dep.mask for dep in spec.dependencies):
                spec.mask = "One or more dependencies masked"
                changed = True


def load(files: list[Path], ids: list[str] | None = None) -> list[ResolvedSpec]:
    """Load cached test specs.  Dependency resolution is performed.

    Args:
      files: file paths to load
      ids: only return these ids

    Returns:
      Loaded test specs
    """

    # Specs must be loaded in static order so that depedencies are correct
    map: dict[str, dict] = {}
    graph: dict[str, list[str]] = {}
    for file in files:
        with open(file) as fh:
            item = json.load(fh)
        map[item["id"]] = item
        graph[item["id"]] = [d["id"] for d in item["dependencies"]]

    # Lookup table for dependencies that have been resolved
    lookup: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        spec_ids = ts.get_ready()
        for id in spec_ids:
            # Replace dependencies with actual references
            spec = ResolvedSpec.from_dict(map[id], lookup)
            lookup[id] = spec
        ts.done(*spec_ids)

    # At this point, lookup contains all the resolved specs
    if not ids:
        return list(lookup.values())

    ids_to_load: set[str] = set()
    for id in ts.static_order():
        if ids_to_load and id not in ids_to_load:
            lookup[id].mask = "==MASKED=="
    return [spec for spec in lookup.values() if not spec.mask]


def generate_specs(
    generators: list["AbstractTestGenerator"],
    on_options: list[str] | None = None,
) -> list[ResolvedSpec]:
    """Generate test cases and filter based on criteria"""
    from .testcase import TestCase as LegacyTestCase

    msg = "@*{Generating} test cases"
    logger.log(logging.INFO, msg, extra={"end": "..."})
    created = time.monotonic()
    try:
        locked: list[list[LegacyTestCase | DraftSpec]]
        locked = starmap(lock_file, [(f, on_options) for f in generators])
        drafts: list[DraftSpec] = []
        for group in locked:
            for spec in group:
                if isinstance(spec, LegacyTestCase):
                    drafts.append(DraftSpec.from_legacy_testcase(spec))
                else:
                    drafts.append(spec)
        nc, ng = len(drafts), len(generators)
    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - created)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)
    logger.info("@*{Generated} %d test cases from %d generators" % (nc, ng))

    duplicates = find_duplicates(drafts)
    if duplicates:
        logger.error("Duplicate test IDs generated for the following test cases")
        for id, dspecs in duplicates.items():
            logger.error(f"{id}:")
            for spec in dspecs:
                logger.log(
                    logging.EMIT, f"  - {spec.display_name}: {spec.file_path}", extra={"prefix": ""}
                )
        raise ValueError("Duplicate test IDs in test suite")

    return resolve(drafts)


def lock_file(file: "AbstractTestGenerator", on_options: list[str] | None):
    return file.lock(on_options=on_options)


def find_duplicates(specs: list["DraftSpec"]) -> dict[str, list["DraftSpec"]]:
    ids = [spec.id for spec in specs]
    duplicate_ids = {id for id in ids if ids.count(id) > 1}
    duplicates: dict[str, list["DraftSpec"]] = {}
    for id in duplicate_ids:
        duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
    return duplicates


@dataclasses.dataclass
class Status:
    value: str = "created"
    details: str | None = None


class ExecutionPolicy(Protocol):
    def command(self, spec: TestSpec) -> list[str]: ...


@dataclasses.dataclass
class ExecutionSpace:
    root: Path

    def create(self):
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def enter(self) -> Generator[None, None, None]:
        self.create()
        with filesystem.working_dir(self.root):
            yield


@dataclasses.dataclass
class TimeKeeper:
    started_on: str = dataclasses.field(default="NA", init=False)
    finished_on: str = dataclasses.field(default="NA", init=False)
    time: float = dataclasses.field(default=-1.0, init=False)
    duration: float = dataclasses.field(default=-1.0, init=False)

    def start(self) -> None:
        self.time = time.monotonic()
        self.started_on = datetime.datetime.now().isoformat(timespec="microseconds")

    def stop(self) -> None:
        self.duration = time.monotonic() - self.time
        self.finished_on = datetime.datetime.now().isoformat(timespec="microseconds")

    @contextmanager
    def timeit(self) -> Generator["TimeKeeper", None, None]:
        try:
            self.start()
            yield self
        finally:
            self.stop()


@dataclasses.dataclass
class Measurements:
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def add_measurement(self, name: str, value: Any):
        self.data[name] = value


class TestCase:
    def __init__(self, spec: TestSpec, workspace: ExecutionSpace) -> None:
        self.spec = spec
        self.workspace = workspace
        self.status = Status()
        self.tk = TimeKeeper()

    def setup(self) -> None:
        with self.workspace.enter():
            config.pluginmanager.hook.canary_testcase_setup(spec=self.spec)

    def teardown(self) -> None:
        with self.workspace.enter():
            config.pluginmanager.hook.canary_testcase_teardown(spec=self.spec)

    def run(self) -> int:
        with self.workspace.enter():
            try:
                self.status.value = "running"
                with open("spec.lock", "w") as fh:
                    self.spec.dump(fh)
                measurements = Measurements()
                with self.tk.timeit():
                    proc = config.pluginmanager.hook.canary_testcase_run(
                        spec=self.spec, measurements=measurements
                    )
            except Exception:
                self.status.value = "failed"
                raise
            else:
                returncode = proc.returncode
                if returncode == self.spec.xstatus:
                    self.status.value = "success"
                else:
                    self.status.value = "failed"
            finally:
                record = {
                    "status": dataclasses.asdict(self.status),
                    "spec": self.spec.asdict(),
                    "timekeeper": dataclasses.asdict(self.tk),
                    "measurements": dataclasses.asdict(measurements),
                }
                with open("record.json", "w") as fh:
                    json.dump(record, fh, cls=PathEncoder)
        return returncode


class PythonFilePolicy(ExecutionPolicy):
    def command(self, spec: TestSpec) -> list[str]:
        args: list[str] = [sys.executable, spec.file.name]
        if script_args := config.getoption("script_args"):
            args.extend(script_args)
        return args


class ShellPolicy(ExecutionPolicy):
    def command(self, spec: TestSpec) -> list[str]:
        raise NotImplementedError
        args: list[str] = ["sh", spec.file.name]
        if script_args := config.getoption("script_args"):
            args.extend(script_args)
        return args


def isrel(path1: str | None, path2: str) -> bool:
    if path1 is None:
        return False
    return os.path.abspath(path1).startswith(os.path.abspath(path2))


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)


class MissingSourceError(Exception):
    pass


class DependencyResolutionFailed(Exception):
    pass


class InvalidTypeError(Exception):
    def __init__(self, name, value):
        class_name = value.__class__.__name__
        super().__init__(f"expected type({name})=type({value!r})=int, not {class_name}")


class MutuallyExclusiveParametersError(Exception):
    def __init__(self, name1, name2):
        super().__init__(f"{name1} and {name2} are mutually exclusive parameters")


class UnresolvedDependenciesErrors(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))
