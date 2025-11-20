# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import fnmatch
import hashlib
import itertools
import math
import os
import shlex
import string
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from graphlib import TopologicalSorter
from pathlib import Path
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import Protocol

from . import config
from .util import json_helper as json
from .util import logging
from .util.string import stringify

if TYPE_CHECKING:
    from .legacy.testcase import TestCase as LegacyTestCase

logger = logging.get_logger(__name__)
select_sygil = "/"


class Named(Protocol):
    id: str
    file_root: Path
    file_path: Path
    family: str
    parameters: dict[str, Any]
    rparameters: dict[str, int]

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
        return str(self.file_path.parent / self.name)

    @cached_property
    def display_name(self: Named) -> str:
        name = self.family
        if p := self.s_params():
            name = f"{name}[{p}]"
        return name

    def s_params(self: Named, sep: str = ",") -> str | None:
        if self.parameters:
            parts = [f"{p}={stringify(self.parameters[p])}" for p in sorted(self.parameters.keys())]
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
            parameters["np"] = self.rparameters["cpus"]
        if "nnode" not in self.parameters:
            parameters["nnode"] = self.rparameters["nodes"]
        if "ndevice" not in self.parameters:
            parameters["ndevice"] = self.rparameters["gpus"]
        if rt := getattr(self, "runtime", None):
            parameters["runtime"] = float(rt)
        return parameters

    @cached_property
    def match_names(self) -> tuple[str, ...]:
        return (
            self.id,
            self.name,
            self.family,
            self.fullname,
            self.display_name,
            str(self.file_path),
            str(self.file_path.parent / self.display_name),
        )

    def required_resources(self) -> list[dict[str, Any]]:
        reqd: list[dict[str, Any]] = []
        for name, value in self.rparameters.items():
            if name == "nodes":
                continue
            reqd.extend([{"type": name, "slots": 1} for _ in range(value)])
        return reqd

    def asdict(self, shallow: bool = False) -> dict:
        return dataclasses.asdict(self)

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), **kwargs)

    def matches(self, arg: str) -> bool:
        if arg.startswith(select_sygil) and not Path(arg).exists():
            arg = arg[1:]
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
    dep_done_criteria: list[str]
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
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    environment: dict[str, str] = dataclasses.field(default_factory=dict)
    environment_modifications: dict[str, str] = dataclasses.field(default_factory=dict)
    cache: dict[str, str] = dataclasses.field(default_factory=dict, init=False)

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
        d.pop("cache", None)
        self = TestSpec(**d)  # ty: ignore[missing-argument]
        return self

    def set_default_timeout(self) -> None:
        """Sets the default timeout.  If runtime statistics have been collected those will be used,
        otherwise the timeout will be based on the presence of duration-like keywords (fast and
        long being the builtin defaults)
        """
        t = self.cache.get("metrics:time")
        if t is not None:
            max_runtime = t["max"]
            if max_runtime < 5.0:
                timeout = 120.0
            elif max_runtime < 120.0:
                timeout = 360.0
            elif max_runtime < 300.0:
                timeout = 900.0
            elif max_runtime < 600.0:
                timeout = 1800.0
            else:
                timeout = 2.0 * max_runtime
        else:
            if t := config.get("timeout:*"):
                timeout = float(t)
            else:
                for keyword in self.keywords:
                    if t := config.get(f"timeout:{keyword}"):
                        timeout = float(t)
                        break
                else:
                    timeout = config.get("timeout:default")
        self._timeout = float(timeout)


@dataclasses.dataclass
class ResolvedSpec(SpecCommons):
    id: str
    file_root: Path
    file_path: Path
    family: str
    dependencies: list["ResolvedSpec"]
    dep_done_criteria: list[str]
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
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    environment: dict[str, str] = dataclasses.field(default_factory=dict)
    environment_modifications: list[dict[str, str]] = dataclasses.field(default_factory=list)

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

    def finalize(self, dependencies: list["TestSpec"]) -> TestSpec:
        return TestSpec(
            id=self.id,
            file_root=self.file_root,
            file_path=self.file_path,
            family=self.family,
            dependencies=dependencies,
            dep_done_criteria=self.dep_done_criteria,
            keywords=self.keywords,
            parameters=self.parameters,
            rparameters=self.rparameters,
            assets=self.assets,
            baseline=self.baseline,
            artifacts=self.artifacts,
            exclusive=self.exclusive,
            timeout=self.timeout,
            xstatus=self.xstatus,
            preload=self.preload,
            modules=self.modules,
            rcfiles=self.rcfiles,
            owners=self.owners,
            mask=self.mask,
            attributes=self.attributes,
            environment=self.environment,
            environment_modifications=self.environment_modifications,
        )


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
        if isinstance(self.pattern, list):
            self.patterns = self.pattern
            self.pattern = " ".join(self.pattern)
        else:
            self.patterns = shlex.split(self.pattern)
        if self.expects is None:
            self.expects = "+"

    def matches(self, spec: "DraftSpec") -> bool:
        names = {
            spec.id,
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
    environment: dict[str, str] = dataclasses.field(default_factory=dict)
    environment_modifications: list[dict[str, str]] = dataclasses.field(default_factory=list)
    id: str = ""

    # Fields that are generated in __post_init__
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
        if not self.id:
            self.id = self._generate_default_id()

        # We make sure objects have the right type, in case any were passed in as name=None
        if self.timeout is None:
            self.timeout = -1.0
        if self.timeout < 0 or self.timeout is None:
            self.timeout = self._default_timeout()
        if self.xstatus is None:
            self.xstatus = 0
        self.keywords = self.keywords or []
        self.file_resources = self.file_resources or []
        self.parameters = self._validate_parameters(self.parameters or {})
        self.assets = self._generate_assets(self.file_resources or {})
        self.baseline_actions = self._generate_baseline_actions(self.baseline or [])
        self.exclusive = bool(self.exclusive)
        self.dependency_patterns = self._generate_dependency_patterns(self.dependencies or [])
        self._generate_analyze_action()

    def resolve(
        self, dependencies: list["ResolvedSpec"], dep_done_criteria: list[str] | None = None
    ) -> "ResolvedSpec":
        errors: list[str] = []
        for dp in self.dependency_patterns:
            if e := dp.verify():
                errors.extend(e)
        dep_done_criteria = dep_done_criteria or ["success"] * len(dependencies)
        if errors:
            raise UnresolvedDependenciesErrors(errors)
        return ResolvedSpec(
            id=self.id,
            file_root=self.file_root,
            file_path=self.file_path,
            family=self.family,
            dependencies=dependencies,
            dep_done_criteria=dep_done_criteria,
            keywords=self.keywords,
            parameters=self.parameters,
            rparameters=self.rparameters,
            assets=self.assets,
            baseline=self.baseline_actions,
            artifacts=self.artifacts,
            exclusive=self.exclusive,
            timeout=self.timeout,
            xstatus=self.xstatus,
            preload=self.preload,
            modules=self.modules,
            rcfiles=self.rcfiles,
            owners=self.owners,
            mask=self.mask,
            attributes=self.attributes,
            environment=self.environment,
            environment_modifications=self.environment_modifications,
        )

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
        if cli_timeouts := config.getoption("timeout"):
            for keyword in self.keywords:
                if t := cli_timeouts.get(keyword):
                    return float(t)
            if t := cli_timeouts.get("*"):
                return float(t)
        for keyword in self.keywords:
            if t := config.get(f"timeout:{keyword}"):
                return float(t)
        if t := config.get("timeout:all"):
            return float(t)
        return float(config.get("timeout:default"))

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

    def _generate_analyze_action(self):
        if analyze := self.attributes.get("analyze"):
            if analyze.startswith("-"):
                self.attributes["script_args"] = [analyze]
            else:
                src: Path
                if os.path.exists(analyze):
                    src = Path(analyze).absolute()
                else:
                    src = self.file.parent / analyze
                if not src.exists():
                    logger.warning(f"{self}: analyze script {analyze} not found")
                self.attributes["alt_script"] = src.name
                # flag is a script to run during analysis, check if it is going to be copied/linked
                for asset in self.assets:
                    if asset.action in ("link", "copy") and src.name == asset.src.name:
                        break
                else:
                    asset = Asset(src, src.name, action="link")
                    self.assets.append(asset)

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
        parameters: dict[str, str] = {}
        for key, val in self.parameters.items():
            parameters[key] = stringify(val)
        for arg in args:
            if isinstance(arg, DependencyPatterns):
                for i, f in enumerate(arg.patterns):
                    t = string.Template(f)
                    arg.patterns[i] = t.safe_substitute(**parameters)
                dependency_patterns.append(arg)
            else:
                t = string.Template(arg)
                pattern = t.safe_substitute(**parameters)
                dep_pattern = DependencyPatterns(pattern=pattern)
                dependency_patterns.append(dep_pattern)
        return dependency_patterns

    def _generate_default_id(self) -> str:
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


def resolve_naive(draft_specs: list[DraftSpec] | list[ResolvedSpec]) -> list[ResolvedSpec]:
    pm = logger.progress_monitor("@*{Resolving} test spec dependencies")
    graph: defaultdict[str, list[str]] = defaultdict(list)
    draft_lookup: defaultdict[str, list[str]] = defaultdict(list)
    dep_done_criteria: defaultdict[str, list[str]] = defaultdict(list)
    map: dict[str, DraftSpec] = {d.id: d for d in draft_specs}
    for spec in draft_specs:
        if isinstance(spec, ResolvedSpec):
            graph[spec.id] = [_.id for _ in spec.dependencies]
        elif not spec.dependency_patterns:
            graph[spec.id] = []
        else:
            for dp in spec.dependency_patterns:
                deps = [u for u in draft_specs if u is not spec and dp.matches(u)]
                dp.update(*[u.id for u in deps])
                draft_lookup[spec.id].extend([_.id for _ in deps])
                dep_done_criteria[spec.id].extend([dp.result_match] * len(deps))
            graph[spec.id] = draft_lookup[spec.id]

    errors: defaultdict[str, list[str]] = defaultdict(list)
    lookup: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            spec = map[id]
            if isinstance(spec, ResolvedSpec):
                lookup[id] = spec
                continue
            dependencies: list[ResolvedSpec] = [lookup[id_] for id_ in draft_lookup[id]]
            try:
                spec = spec.resolve(dependencies, dep_done_criteria[spec.id])
            except UnresolvedDependenciesErrors as e:
                errors[spec.fullname].extend(e.errors)
            lookup[id] = spec
        ts.done(*ids)
    pm.done(status="done" if not errors else "failed")

    if errors:
        msg: list[str] = ["Dependency resolution failed:"]
        for name, issues in errors.items():
            msg.append(f"  {name}")
            msg.extend(f"  • {p}" for p in issues)
        raise DependencyResolutionFailed("\n".join(msg))
    return list(lookup.values())


def resolve(specs: list[DraftSpec] | list[ResolvedSpec]) -> list[ResolvedSpec]:
    pm = logger.progress_monitor("@*{Resolving} test spec dependencies")

    # Separate specs into resolved and draft
    draft_specs: list[DraftSpec] = []
    resolved_specs: list[ResolvedSpec] = []
    spec_map: dict[str, DraftSpec | ResolvedSpec] = {}

    # Build indices
    unique_name_idx: dict[str, str] = {}
    non_unique_idx: dict[str, list[str]] = defaultdict(list)

    for spec in specs:
        spec_map[spec.id] = spec

        if isinstance(spec, ResolvedSpec):
            resolved_specs.append(spec)
        else:
            draft_specs.append(spec)

        # Index unique identifiers (for both draft and resolved)
        unique_name_idx[spec.id] = spec.id

        # Index non-unique identifiers (for both draft and resolved)
        non_unique_idx[spec.name].append(spec.id)
        non_unique_idx[spec.fullname].append(spec.id)
        non_unique_idx[spec.display_name].append(spec.id)
        non_unique_idx[spec.family].append(spec.id)
        non_unique_idx[str(spec.file_path)].append(spec.id)
        non_unique_idx[str(spec.file_path.parent / spec.display_name)].append(spec.id)

    # All specs that can be matched (both draft and resolved)
    matchable_specs = draft_specs + resolved_specs

    # Build dependency graph in parallel, specs will be added as they resolve
    graph: dict[str, list[str]] = {r.id: [_.id for _ in r.dependencies] for r in resolved_specs}
    draft_lookup: dict[str, list[str]] = {}
    dep_done_criteria: dict[str, list[str]] = {}

    results: list[tuple[str, list[str], list[str]]]
    if os.getenv("CANARY_SERIAL_SPEC_RESOLUTION"):
        results = _resolve_dependencies_serial(
            draft_specs, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )
    else:
        results = _resolve_dependencies_parallel(
            draft_specs, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )

    # Merge results
    for spec_id, matches, done_criteria in results:
        graph[spec_id] = matches
        draft_lookup[spec_id] = matches
        dep_done_criteria[spec_id] = done_criteria

    # Resolve dependencies using topological sort (this is fast, keep sequential)
    errors: defaultdict[str, list[str]] = defaultdict(list)
    lookup: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()

    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            spec = spec_map[id]
            if isinstance(spec, ResolvedSpec):
                lookup[id] = spec
            else:
                dep_ids = draft_lookup.get(id, [])
                dependencies = [lookup[dep_id] for dep_id in dep_ids]

                try:
                    spec = spec.resolve(dependencies, dep_done_criteria.get(id, []))
                except UnresolvedDependenciesErrors as e:
                    errors[spec.fullname].extend(e.errors)

                lookup[id] = spec
        ts.done(*ids)

    pm.done(status="done" if not errors else "failed")

    if errors:
        msg: list[str] = ["Dependency resolution failed:"]
        for name, issues in errors.items():
            msg.append(f"  {name}")
            msg.extend(f"  • {p}" for p in issues)
        raise DependencyResolutionFailed("\n".join(msg))

    return list(lookup.values())


def _resolve_dependencies_serial(
    specs_to_resolve: list[DraftSpec],
    matchable_specs: list[DraftSpec | ResolvedSpec],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, DraftSpec | ResolvedSpec],
) -> list[tuple[str, list[str], list[str]]]:
    """Resolve dependencies serially for debugging"""
    results = []
    for spec in specs_to_resolve:
        if not spec.dependency_patterns:
            results.append(_resolve_empty(spec))
        else:
            results.append(
                _resolve_spec_dependencies(
                    spec, matchable_specs, unique_name_idx, non_unique_idx, spec_map
                )
            )
    return results


def _resolve_dependencies_parallel(
    specs_to_resolve: list[DraftSpec],
    matchable_specs: list[DraftSpec | ResolvedSpec],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, DraftSpec | ResolvedSpec],
) -> list[tuple[str, list[str], list[str]]]:
    """Resolve dependencies in parallel, returning (spec_id, match_ids, done_criteria)"""

    if not specs_to_resolve:
        return []

    num_workers = min(os.cpu_count() or 4, len(specs_to_resolve))

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for spec in specs_to_resolve:
            if not spec.dependency_patterns:
                futures.append(executor.submit(_resolve_empty, spec))
            else:
                futures.append(
                    executor.submit(
                        _resolve_spec_dependencies,
                        spec,
                        matchable_specs,
                        unique_name_idx,
                        non_unique_idx,
                        spec_map,
                    )
                )

        results = [future.result() for future in futures]

    return results


def _resolve_empty(spec: DraftSpec) -> tuple[str, list[str], list[str]]:
    """Fast path for specs with no dependencies"""
    return (spec.id, [], [])


def _resolve_spec_dependencies(
    spec: DraftSpec,
    matchable_specs: list[DraftSpec | ResolvedSpec],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, DraftSpec | ResolvedSpec],
) -> tuple[str, list[str], list[str]]:
    """Resolve dependencies for a single spec"""
    matches: list[str] = []
    done_criteria: list[str] = []

    for dp in spec.dependency_patterns:
        deps = _find_matching_specs(
            dp, spec, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )
        dep_ids = [d.id for d in deps]
        dp.update(*dep_ids)
        matches.extend(dep_ids)
        done_criteria.extend([dp.result_match] * len(deps))

    return (spec.id, matches, done_criteria)


def _find_matching_specs(
    dp: DependencyPatterns,
    source_spec: DraftSpec,
    matchable_specs: list[DraftSpec | ResolvedSpec],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, DraftSpec | ResolvedSpec],
) -> list[DraftSpec | ResolvedSpec]:
    """Optimized pattern matching using indices where possible"""
    matches: set[str] = set()
    matched_specs: list[DraftSpec | ResolvedSpec] = []

    for pattern in dp.patterns:
        # Check exact matches first before resorting to glob matching
        candidates: list[DraftSpec | ResolvedSpec] = []
        if pattern in unique_name_idx:
            spec_id = unique_name_idx[pattern]
            candidates.append(spec_map[spec_id])
        elif pattern in non_unique_idx:
            spec_ids = non_unique_idx[pattern]
            candidates.extend([spec_map[spec_id] for spec_id in spec_ids])

        for spec in candidates:
            if spec.id != source_spec.id and spec.id not in matches:
                matches.add(spec.id)
                matched_specs.append(spec)

        if not matched_specs:
            # Glob pattern - check all matchable specs (draft AND resolved)
            for spec in matchable_specs:
                if spec.id == source_spec.id or spec.id in matches:
                    continue

                if _pattern_matches_spec(pattern, spec):
                    matches.add(spec.id)
                    matched_specs.append(spec)

    return matched_specs


def _pattern_matches_spec(pattern: str, spec: DraftSpec | ResolvedSpec) -> bool:
    """Check if pattern matches any of the spec's names"""
    names = (
        spec.id,
        spec.name,
        spec.family,
        spec.fullname,
        spec.display_name,
        str(spec.file_path),
        str(spec.file_path.parent / spec.display_name),
    )

    for name in names:
        if fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def finalize(resolved_specs: list[ResolvedSpec]) -> list[TestSpec]:
    pm = logger.progress_monitor("@*{Finalizing} test specs")
    map: dict[str, ResolvedSpec] = {}
    graph: dict[str, list[str]] = {}
    for resolved_spec in resolved_specs:
        map[resolved_spec.id] = resolved_spec
        graph[resolved_spec.id] = [s.id for s in resolved_spec.dependencies]
    lookup: dict[str, TestSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            resolved = map[id]
            dependencies: list[TestSpec] = [lookup[dep.id] for dep in resolved.dependencies]
            spec = resolved.finalize(dependencies)
            lookup[id] = spec
        ts.done(*ids)
    pm.done()
    return list(lookup.values())


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)


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
