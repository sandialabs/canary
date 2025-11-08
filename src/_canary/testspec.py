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
from .util import graph
from .util import logging
from .util.parallel import starmap
from .util.string import stringify

if TYPE_CHECKING:
    from .generator import AbstractTestGenerator
    from .testcase import TestCase

logger = logging.get_logger(__name__)


@dataclasses.dataclass(frozen=True)
class TestSpec:
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
    command: list[str] = dataclasses.field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.id)

    @cached_property
    def file(self) -> Path:
        return self.file_root / self.file_path

    @cached_property
    def name(self) -> str:
        name = self.family
        if self.parameters:
            s_params = [f"{p}={stringify(self.parameters[p])}" for p in self.parameters]
            name = f"{name}.{'.'.join(s_params)}"
        return name

    @cached_property
    def fullname(self) -> str:
        return str(self.file_path / self.name)

    @cached_property
    def display_name(self) -> str:
        name = self.family
        if self.parameters:
            s_params = [f"{p}={stringify(self.parameters[p])}" for p in self.parameters]
            name = f"{name}[{','.join(s_params)}]"
        return name

    def pretty_name(self) -> str:
        if not self.parameters:
            return self.name
        parts: list[str] = []
        colors = itertools.cycle("bmgycr")
        for key in sorted(self.parameters):
            value = stringify(self.parameters[key])
            parts.append("@%s{%s=%s}" % (next(colors), key, value))
        return f"{self.name}[{','.join(parts)}]"

    def __post_init__(self) -> None:
        if not self.command:
            command = [sys.executable, self.file.name]
            object.__setattr__(self, "command", command)

    def asdict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TestSpec":
        d["file_root"] = Path(d.pop("file_root"))
        d["file_path"] = Path(d.pop("file_path"))
        dependencies: list[TestSpec] = []
        for dep in d["dependencies"]:
            dependencies.append(TestSpec.from_dict(dep))
        d["dependencies"] = dependencies
        assets: list[Asset] = []
        for a in d["assets"]:
            assets.append(Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]))
        d["assets"] = assets
        self = TestSpec(**d)
        return self

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, cls=PathEncoder, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), cls=PathEncoder, **kwargs)

    @classmethod
    def load(cls, file: IO[Any]) -> "TestSpec":
        d = json.load(file)
        return cls.from_dict(d)


class PathEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


@dataclasses.dataclass
class Asset:
    src: Path
    dst: str
    action: Literal["copy", "link"]


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
class DraftSpec:
    """Temporary object used to hold TestCase properties"""

    file_root: Path
    file_path: Path
    family: str = ""
    dependencies: list[str | DependencyPatterns] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    sources: dict[str, list[tuple[str, str | None]]] = dataclasses.field(default_factory=list)
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
    command: list[str] = dataclasses.field(default_factory=list)

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

    def __hash__(self) -> int:
        return hash(self.id)

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
        self.sources = self.sources or []
        self.parameters = self._validate_parameters(self.parameters or {})
        self.assets = self._generate_assets(self.assets or {})
        self.baseline_actions = self._generate_baseline_actions(self.baseline or [])
        self.exclusive = bool(self.exclusive)
        self.dependency_patterns = self._generate_dependency_patterns(self.dependencies or [])

        if not self.command:
            self.command = [sys.executable, self.file.name]

    @cached_property
    def file(self) -> Path:
        return self.file_root / self.file_path

    @cached_property
    def name(self) -> str:
        name = self.family
        if self.parameters:
            s_params = [f"{p}={stringify(self.parameters[p])}" for p in self.parameters]
            name = f"{name}.{'.'.join(s_params)}"
        return name

    @cached_property
    def fullname(self) -> str:
        return str(self.file_path.parent / self.name)

    @cached_property
    def display_name(self) -> str:
        name = self.family
        if self.parameters:
            s_params = [f"{p}={stringify(self.parameters[p])}" for p in self.parameters]
            name = f"{name}[{','.join(s_params)}]"
        return name

    def required_resources(self) -> list[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = []
        for name, value in self.parameters.items():
            if name == "resource::nodes":
                continue
            if name.startswith("resource::"):
                assert isinstance(value, int)
                name = name[10:]
                group.extend([{"type": name, "slots": 1} for _ in range(value)])
        # by default, only one resource group is returned
        return [group]

    def asdict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DraftSpec":
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
        draft = DraftSpec(**attrs)

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
        draft.resolved_dependencies = [DraftSpec.from_dict(ds) for ds in d["resolved_dependencies"]]
        draft.resolved = d["resolved"]
        return draft

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, cls=PathEncoder, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), cls=PathEncoder, **kwargs)

    @classmethod
    def load(cls, file: IO[Any]) -> "DraftSpec":
        d = json.load(file)
        return cls.from_dict(d)

    @property
    def implicit_keywords(self) -> list[str]:
        """Implicit keywords, used for some filtering operations"""
        kwds = {self.name, self.family, str(self.file_root / self.file_path)}
        return list(kwds)

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

    def matches(self, arg: str) -> bool:
        if self.id.startswith(arg):
            return True
        if self.display_name == arg:
            return True
        if self.name == arg:
            return True
        return False

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

    def _generate_assets(self, sources: dict[str, list[tuple[str, str | None]]]) -> list[Asset]:
        assets: list[Asset] = []
        dirname = self.file.parent
        for action, args in sources.items():
            src: Path = Path(args[0])
            if not src.is_absolute():
                src = dirname / src
            if not src.exists():
                logger.debug(f"{self}: {action} resource file {str(src)} not found")
            dst: str = args[1] if args[1] is not None else src.name
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

    @classmethod
    def from_legacy_testcase(cls, case: "TestCase") -> "DraftSpec":
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
            dp = DependencyPatterns(pattern=pattern, expects=ud.expect, result_match=ud.result)
            dependency_patterns.append(dp)
        spec.dependency_patterns.clear()
        spec.dependency_patterns.extend(dependency_patterns)
        assets: list[Asset] = []
        for a in case.assets:
            assets.append(Asset(src=Path(a.src), dst=a.dst or Path(a.src).name, action=a.action))
        spec.assets.clear()
        spec.assets.extend(assets)
        if case.artifacts:
            spec.artifacts.clear()
            spec.artifacts.extend(case.artifacts)
        return spec


def resolve_dependencies(draft_specs: list[DraftSpec]) -> None:
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


def finalize(draft_specs: list[DraftSpec]) -> list[TestSpec]:
    map: dict[str, DraftSpec] = {}
    graph: dict[str, list[str]] = {}
    for draft in draft_specs:
        if not draft.is_resolved():
            raise ValueError(f"{draft}: cannot finalize unresolved drafts")
    for draft in draft_specs:
        map[draft.id] = draft
        graph[draft.id] = [d.id for d in draft.resolved_dependencies]
    specs: dict[str, TestSpec] = {}
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
            spec = TestSpec(
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
                command=draft.command,
            )
            specs[id] = spec
        ts.done(*ids)
    return list(specs.values())


def apply_masks(
    drafts: list[DraftSpec],
    *,
    keyword_exprs: list[str] | None = None,
    parameter_expr: str | None = None,
    owners: set[str] | None = None,
    regex: str | None = None,
    ids: list[str] | None = None,
    ignore_dependencies: bool = False,
) -> None:
    """Filter test specs (mask test specs that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      ids: Include those tests matching these ids

    """
    msg = "@*{Masking} test specs based on filtering criteria"
    created = time.monotonic()
    logger.log(logging.INFO, msg, extra={"end": "..."})
    rx: re.Pattern | None = None
    try:
        if regex is not None:
            logger.warning("Regular expression search can be slow for large test suites")
            rx = re.compile(regex)

        no_filter_criteria = all(_ is None for _ in (keyword_exprs, parameter_expr, owners, regex))

        owners = set(owners or [])
        order = graph.static_order_ix(drafts)
        for i in order:
            draft = drafts[i]

            if draft.mask:
                continue

            if ids is not None:
                if not any(draft.matches(id) for id in ids):
                    expr = ",".join(ids)
                    draft.mask = "testspec expression @*{%s} did not match" % expr
                continue

            try:
                check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=draft)
            except Exception as e:
                draft.mask = "@*{%s}(%r)" % (e.__class__.__name__, e.args[0])
                continue
            else:
                if not check:
                    draft.mask = check.reason
                    continue

            if owners and not owners.intersection(draft.owners):
                draft.mask = "not owned by @*{%r}" % draft.owners
                continue

            if keyword_exprs is not None:
                kwds = set(draft.keywords)
                kwds.update(draft.implicit_keywords)
                kwd_all = contains_any(("__all__", ":all:"), keyword_exprs)
                if not kwd_all:
                    for keyword_expr in keyword_exprs:
                        match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                        if not match:
                            draft.mask = "keyword expression @*{%r} did not match" % keyword_expr
                            break
                    if draft.mask:
                        continue

            if parameter_expr:
                match = when.when(
                    {"parameters": parameter_expr},
                    parameters=draft.parameters | draft.implicit_parameters,
                )
                if not match:
                    draft.mask = "parameter expression @*{%s} did not match" % parameter_expr
                    continue

            if draft.dependencies and not ignore_dependencies:
                flags = draft.dep_condition_flags()
                if any([flag == "wont_run" for flag in flags]):
                    draft.mask = "one or more dependencies not satisfied"
                    continue

            if rx is not None:
                if not filesystem.grep(rx, draft.file):
                    for asset in draft.assets:
                        if os.path.isfile(asset.src) and filesystem.grep(rx, asset.src):
                            break
                    else:
                        draft.mask = "@*{re.search(%r) is None} evaluated to @*g{True}" % regex
                        continue

            # If we got this far and the draft is not masked, only mask it if no filtering criteria were
            # specified
            if no_filter_criteria and not draft.status.satisfies(("created", "pending", "ready")):
                draft.mask = f"previous status {draft.status.value!r} is not 'ready'"
    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - created)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)

    propagate_masks(drafts)


def propagate_masks(drafts: list[DraftSpec]) -> None:
    changed: bool = True
    while changed:
        changed = False
        for draft in drafts:
            if draft.mask:
                continue
            if any(dep.mask for dep in draft.dependencies):
                draft.mask = "One or more dependencies masked"
                changed = True


def load(files: list[Path], ids: list[str] | None = None) -> list[DraftSpec]:
    """Load cached test specs.  Dependency resolution is performed.

    Args:
      files: file paths to load
      ids: only return these ids

    Returns:
      Loaded test specs
    """
    drafts: list[DraftSpec] = []
    for file in files:
        with open(file) as fh:
            draft = DraftSpec.load(fh)
        assert draft.is_resolved()
        drafts.append(draft)
    map: dict[str, DraftSpec] = {draft.id: draft for draft in drafts}
    graph: dict[str, list[str]] = {draft.id: [d.id for d in draft.dependencies] for draft in drafts}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        draft_ids = ts.get_ready()
        for id in draft_ids:
            # Replace dependencies with actual references
            dependencies = []
            draft = map[id]
            for dp in draft.resolved_dependencies:
                dependencies.append(map[dp.id])
            draft.resolved_dependencies.clear()
            draft.resolved_dependencies.extend(dependencies)
        ts.done(*draft_ids)
    if not ids:
        return drafts
    ids_to_load: set[str] = set()
    for id in ts.static_order():
        if ids_to_load and id not in ids_to_load:
            map[id].mask = "==MASKED=="
    return [draft for draft in drafts if not draft.mask]


def generate_draftspecs(
    generators: list["AbstractTestGenerator"],
    on_options: list[str] | None = None,
) -> list["DraftSpec"]:
    """Generate test cases and filter based on criteria"""
    from .testcase import TestCase

    msg = "@*{Generating} test cases"
    logger.log(logging.INFO, msg, extra={"end": "..."})
    created = time.monotonic()
    try:
        locked: list[list[TestCase | DraftSpec]]
        locked = starmap(lock_file, [(f, on_options) for f in generators])
        drafts: list[DraftSpec] = []
        for group in locked:
            for spec in group:
                if isinstance(spec, TestCase):
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

    resolve_dependencies(drafts)
    for draft in drafts:
        assert draft.is_resolved()

    return drafts


def lock_file(file: "AbstractTestGenerator", on_options: list[str] | None):
    return file.lock(on_options=on_options)


def find_duplicates(specs: list["DraftSpec"]) -> dict[str, list["DraftSpec"]]:
    ids = [spec.id for spec in specs]
    duplicate_ids = {id for id in ids if ids.count(id) > 1}
    duplicates: dict[str, list["DraftSpec"]] = {}
    for id in duplicate_ids:
        duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
    return duplicates


class ExecutionPolicy(Protocol):
    def command(self, spec: TestSpec) -> list[str]: ...


@dataclasses.dataclass
class Status:
    value: str = "created"
    details: str | None = None


@dataclasses.dataclass
class ExecutionSpace:
    root: Path


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


class TestInstance:
    def __init__(self, spec: TestSpec, policy: ExecutionPolicy, workspace: ExecutionSpace) -> None:
        self.spec = spec
        self.policy = policy
        self.workspace = workspace
        self.status = Status()
        self.tk = TimeKeeper()

    def run(self) -> int:
        with self.tk.timeit():
            # do the run
            pass


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
