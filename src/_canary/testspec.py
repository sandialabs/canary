# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import fnmatch
import hashlib
import itertools
import os
import shlex
import string
import sys
from functools import cached_property
from functools import lru_cache
from pathlib import Path
from typing import IO
from typing import Any
from typing import Generic
from typing import Literal
from typing import Sequence
from typing import Type
from typing import TypeVar

from . import config
from .util import json_helper as json
from .util import logging
from .util.string import stringify

logger = logging.get_logger(__name__)
select_sygil = "/"


@dataclasses.dataclass(frozen=True)
class Mask:
    value: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.value and not self.reason:
            raise TypeError("Mask(True) requires a reason")
        elif not self.value and self.reason:
            raise TypeError(f"Mask(False) not compatible with reason {self.reason!r}")

    def __bool__(self) -> bool:
        return self.value

    @classmethod
    def masked(cls, reason: str) -> "Mask":
        return cls(True, reason)

    @classmethod
    def unmasked(cls) -> "Mask":
        return cls(False, None)


T = TypeVar("T", bound="BaseSpec")


@dataclasses.dataclass
class BaseSpec(Generic[T]):
    file_root: Path
    file_path: Path
    family: str = ""
    id: str = ""
    stdout: str = "canary-out.txt"
    stderr: str | None = None  # combine stdout/stderr by default
    dependencies: Sequence[Any] = dataclasses.field(default_factory=list)
    dep_done_criteria: list[str] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    keywords: list[str] = dataclasses.field(default_factory=list)
    assets: list["Asset"] = dataclasses.field(default_factory=list)
    baseline: list[Any] = dataclasses.field(default_factory=list)
    artifacts: list[dict[str, str]] = dataclasses.field(default_factory=list)
    exclusive: bool = False
    timeout: float = -1.0
    xstatus: int = 0
    preload: str | None = None
    modules: list[str] | None = None
    rcfiles: list[str] | None = None
    owners: list[str] | None = None
    environment: dict[str, str] = dataclasses.field(default_factory=dict)
    environment_modifications: list[dict[str, str]] = dataclasses.field(default_factory=list)
    meta_parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return self.display_name()

    def __repr__(self) -> str:
        p = self.family
        if self.parameters:
            p += ", " + ", ".join(f"{k}={self.parameters[k]}" for k in sorted(self.parameters))
        return f"{self.__class__.__name__}({p})"

    def __post_init__(self) -> None:
        self.family = self.family or self.file.stem
        if not self.id:
            self.id = self._generate_default_id()
        if self.timeout is None:
            self.timeout = -1.0
        if self.timeout < 0:
            self.timeout = self._default_timeout()
        if self.xstatus is None:
            self.xstatus = 0
        if "cpus" not in self.parameters | self.meta_parameters:
            self.meta_parameters["cpus"] = 1
        if "gpus" not in self.parameters | self.meta_parameters:
            self.meta_parameters["gpus"] = 0
        self.meta_parameters["runtime"] = self.timeout

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), **kwargs)

    @classmethod
    def from_dict(cls: Type[T], d: dict, lookup: dict[str, T]) -> T:
        d["file_root"] = Path(d.pop("file_root"))
        d["file_path"] = Path(d.pop("file_path"))
        dependencies = [lookup[dep["id"]] for dep in d["dependencies"]]
        d["dependencies"] = dependencies
        assets = [Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]) for a in d["assets"]]
        d["assets"] = assets
        self = cls(**d)  # ty: ignore[missing-argument]
        return self

    @cached_property
    def file(self) -> Path:
        return self.file_root / self.file_path

    @cached_property
    def name(self) -> str:
        name = self.family
        if p := self.s_params(sep="."):
            name = f"{name}.{p}"
        return name

    @cached_property
    def fullname(self) -> str:
        return str(self.file_path.parent / self.name)

    @property
    def execpath(self) -> str:
        if p := self.attributes.get("execpath"):
            return p
        return str(self.file_path.parent / self.name)

    @execpath.setter
    def execpath(self, arg: str) -> None:
        self.attributes["execpath"] = arg

    @lru_cache
    def display_name(
        self, style: Literal["none", "rich", "legacy-color"] = "none", resolve: bool = False
    ) -> str:
        if style == "none":
            return self.name if not resolve else self.fullname
        elif not self.parameters:
            return self.family

        colors = ["blue", "magenta", "green", "yellow", "cyan", "red"]
        color_cycler: itertools.cycle
        if style == "legacy-color":
            color_cycler = itertools.cycle([_[0] for _ in colors])
        else:
            color_cycler = itertools.cycle(colors)
        parts = []
        params = [(p, stringify(self.parameters[p])) for p in sorted(self.parameters)]
        for key, value in params:
            value = stringify(self.parameters[key])
            color = next(color_cycler)
            if style == "legacy-color":
                part = f"@{color}{{{key}={value}}}"
            else:
                part = f"[{color}]{key}={value}[/{color}]"
            parts.append(part)
        name = f"{self.family}.{'.'.join(parts)}"
        if resolve:
            name = f"{self.file_path.parent}/{name}"
        return name

    def s_params(self, sep: str = ",") -> str | None:
        if self.parameters:
            parts = [f"{p}={stringify(self.parameters[p])}" for p in sorted(self.parameters.keys())]
            return sep.join(parts)
        return None

    @property
    def implicit_keywords(self) -> set[str]:
        """Implicit keywords, used for some filtering operations"""
        return {self.id, self.name, self.family, str(self.file)}

    @cached_property
    def match_names(self) -> tuple[str, ...]:
        return (
            self.id,
            self.name,
            self.family,
            self.fullname,
            self.display_name(),
            str(self.file_path),
            str(self.file_path.parent / self.display_name()),
        )

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

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        self.attributes.update(**kwds)

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
        return hasher.hexdigest()

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


@dataclasses.dataclass
class ResolvedSpec(BaseSpec["ResolvedSpec"]):
    baseline: list[dict] = dataclasses.field(default_factory=list)
    dependencies: Sequence["ResolvedSpec"] = dataclasses.field(default_factory=list)
    mask: Mask = dataclasses.field(default_factory=Mask.unmasked)

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        p = self.family
        if self.parameters:
            p += ", " + ", ".join(f"{k}={self.parameters[k]}" for k in sorted(self.parameters))
        return f"{self.__class__.__name__}({p})"

    @classmethod
    def from_dict(cls, d: dict, lookup: dict[str, "ResolvedSpec"]) -> "ResolvedSpec":
        mask = d.pop("mask", None)
        if mask:
            d["mask"] = Mask(mask["value"], mask["reason"])
        return super().from_dict(d, lookup)


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

    def matches(self, spec: "UnresolvedSpec") -> bool:
        names = {
            spec.id,
            spec.name,
            spec.family,
            spec.fullname,
            spec.display_name(),
            spec.display_name(resolve=True),
            str(spec.file_path),
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
class UnresolvedSpec(BaseSpec["UnresolvedSpec"]):
    """Temporary object used to hold test spec properties until a concrete spec can be created
    after dependency resolution"""

    dependencies: Sequence[str | DependencyPatterns] = dataclasses.field(default_factory=list)
    file_resources: dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]] = (
        dataclasses.field(default_factory=dict)
    )
    baseline: list[str | tuple[str, str]] = dataclasses.field(default_factory=list)
    mask: Mask = dataclasses.field(default_factory=Mask.unmasked)
    baseline_actions: list[dict] = dataclasses.field(default_factory=list, init=False)
    dep_patterns: list[DependencyPatterns] = dataclasses.field(default_factory=list, init=False)
    resolved_dependencies: list["UnresolvedSpec"] = dataclasses.field(
        default_factory=list, init=False
    )
    resolved: bool = dataclasses.field(default=False, init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        # We make sure objects have the right type, in case any were passed in as name=None
        self.assets = self._generate_assets(self.file_resources or {})
        self.baseline_actions = self._generate_baseline_actions(self.baseline or [])
        self.dep_patterns = self._generate_dependency_patterns(self.dependencies or [])
        self._generate_analyze_action()

    def __hash__(self) -> int:
        return hash(self.id)

    def resolve(
        self, dependencies: list["ResolvedSpec"], dep_done_criteria: list[str] | None = None
    ) -> "ResolvedSpec":
        errors: list[str] = []
        for dp in self.dep_patterns:
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
            meta_parameters=self.meta_parameters,
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
            stdout=self.stdout,
            stderr=self.stderr,
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

    def _generate_analyze_action(self) -> None:
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

    def _generate_dependency_patterns(
        self, args: Sequence[str | DependencyPatterns]
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


class MutuallyExclusiveParametersError(Exception):
    def __init__(self, name1, name2):
        super().__init__(f"{name1} and {name2} are mutually exclusive parameters")


class UnresolvedDependenciesErrors(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))
