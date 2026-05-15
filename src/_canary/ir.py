# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import fnmatch
import hashlib
import os
import shlex
import string
import sys
import threading
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Literal
from typing import Sequence

from . import config
from .testspec import Artifact
from .testspec import Asset
from .testspec import Mask
from .testspec import ResolvedSpec
from .testspec import SpecDependency
from .util import logging
from .util.string import stringify

FileResourceT = dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]]
logger = logging.get_logger(__name__)


@dataclass
class DependencySpec:
    """String representation of test dependencies

    Dependency resolution is performed after test case discovery.  The ``DependencySpec``
    object holds information needed to perform the resolution.

    Args:
      value: The dependency name or glob pattern.
      expect: For glob patterns, how many dependencies are expected to be found
      result: The test case will run if the dependency exits with this status.  Usually ``success``

    """

    pattern: str
    expects: str | int = "+"
    when: str = "on_success"
    resolves_to: list[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        expects = self.expects
        if not isinstance(expects, (str, int)):
            raise TypeError(f"DependencySpec.expects: invalid type {type(expects).__name__!r}")
        if isinstance(expects, str):
            choices = {"+", "?", "*"}
            if expects not in choices:
                s = ", ".join(sorted(choices))
                msg = f"DependencySpec.expect: invalid choice: {expects!r} (choose from {s})"
                raise TypeError(msg)
        elif expects <= 0:
            raise ValueError(f"DependencySpec.expect: invalid value: {expects!r} (must be > 0)")
        elif expects is None:
            self.expects = "+"

    def matches(self, spec: Any) -> bool:
        choices = {
            spec.name,
            spec.family,
            spec.fullname,
            spec.display_name(),
            spec.display_name(resolve=True),
            str(spec.file_path),
        }
        if self.pattern in choices:
            return True
        for choice in choices:
            for pat in shlex.split(self.pattern):
                if fnmatch.fnmatchcase(choice, pat):
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


class JobSpecIR:
    def __init__(
        self,
        file_root: Path,
        file_path: Path,
        id: str | None = None,
        family: str | None = None,
        stdout: str = "canary-out.txt",
        stderr: str | None = None,  # combine stdout/stderr by default
        dependencies: list[DependencySpec] | None = None,
        parameters: dict[str, Any] | None = None,
        meta_parameters: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        keywords: list[str] | None = None,
        assets: list[Asset] | None = None,
        artifacts: list[Artifact] | None = None,
        exclusive: bool = False,
        timeout: float = -1.0,
        xstatus: int = 0,
        preload: str | None = None,
        modules: list[str] | None = None,
        rcfiles: list[str] | None = None,
        owners: list[str] | None = None,
        environment: dict[str, str | None] | None = None,
        command: list[str] | None = None,
        file_resources: FileResourceT | None = None,
        mask: Mask = Mask.unmasked(),
        baseline: list[str | tuple[str, str]] | None = None,
        view_path: str | None = None,
        exec_path: str | None = None,
    ):
        self.file_root: Path = Path(file_root)
        self.file_path: Path = Path(file_path)
        self.file = self.file_root / self.file_path
        self.family: str = family or self.file.stem
        self.parameters: dict[str, Any] = parameters or {}
        self.meta_parameters: dict[str, Any] = meta_parameters or {}
        self.stdout: str = stdout
        self.stderr: str | None = stderr
        self.dependencies: list[DependencySpec] = self.build_dependencies(dependencies or [])
        self.attributes: dict[str, Any] = attributes or {}
        self.keywords: list[str] = keywords or []
        self.assets: list[Asset] = assets or []
        self.assets = self.assets or self.build_assets(file_resources or {})
        self.artifacts: list[Artifact] = artifacts or []
        self.exclusive = exclusive
        if timeout < 0:
            timeout = self._default_timeout()
        self.timeout: float = timeout
        self.meta_parameters["runtime"] = self.timeout
        self.xstatus: int = xstatus
        self.preload: str | None = preload
        self.modules: list[str] | None = modules
        self.rcfiles: list[str] | None = rcfiles
        self.owners: list[str] | None = owners
        self.environment: dict[str, str | None] = environment or {}
        self.command = command or []
        self.mask = mask
        self.baseline = self.build_baseline_actions(baseline or [])
        self.exec_path: str | None = exec_path
        self.view_path: str | None = view_path

        if id is None:
            kwds = self.parameters | self.meta_parameters
            kwds.pop("runtime")
            id = build_id(self.family, self.file_root / self.file_path, **kwds)
        self.id: str = id

    def __hash__(self) -> int:
        return hash(self.id)

    def add_artifact(
        self, pattern: str, when: Literal["always", "never", "on_failure", "on_success"] = "always"
    ) -> None:
        self.artifacts.append(Artifact(pattern=pattern, when=when))

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        self.attributes.update(**kwds)

    def _default_timeout(self) -> float:
        if cli_timeouts := config.getoption("timeout"):
            for keyword in self.keywords:
                if t := cli_timeouts.get(keyword):
                    return float(t)
            if t := cli_timeouts.get("*"):
                return float(t)
        for keyword in self.keywords:
            if t := config.get(f"run:timeout:{keyword}"):
                return float(t)
        if t := config.get("run:timeout:all"):
            return float(t)
        return float(config.get("run:timeout:default"))

    def finalize(self, lookup: dict[str, "ResolvedSpec"]) -> "ResolvedSpec":
        errors: list[str] = []
        for dp in self.dependencies:
            errors.extend(dp.verify())
        if errors:
            raise UnresolvedDependenciesErrors(errors)
        deps: list[SpecDependency] = []
        for dp in self.dependencies:
            for dep_id in dp.resolves_to:
                deps.append(SpecDependency(spec=lookup[dep_id], when=dp.when))
        return ResolvedSpec(
            file_root=self.file_root,
            file_path=self.file_path,
            family=self.family,
            dependencies=deps,
            keywords=self.keywords,
            parameters=self.parameters,
            meta_parameters=self.meta_parameters,
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
            stdout=self.stdout,
            stderr=self.stderr,
            id=self.id,
            command=self.command,
            exec_path=self.exec_path,
            view_path=self.view_path,
        )

    def build_assets(self, file_resources: FileResourceT) -> list[Asset]:
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

    def build_baseline_actions(self, items: list[str | tuple[str, str]]) -> list[dict]:
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

    def build_dependencies(self, args: Sequence[str | DependencySpec]) -> list[DependencySpec]:
        dependency_specs: list[DependencySpec] = []
        parameters: dict[str, str] = {}
        for key, val in self.parameters.items():
            parameters[key] = stringify(val)
        for arg in args:
            if isinstance(arg, DependencySpec):
                t = string.Template(arg.pattern)
                arg.pattern = t.safe_substitute(**parameters)
                dependency_specs.append(arg)
            else:
                t = string.Template(arg)
                pattern = t.safe_substitute(**parameters)
                dep_pattern = DependencySpec(pattern=pattern)
                dependency_specs.append(dep_pattern)
        return dependency_specs

    @property
    def name(self) -> str:
        name = self.family
        if self.parameters:
            parts = [f"{p}={stringify(self.parameters[p])}" for p in sorted(self.parameters.keys())]
            p = ".".join(parts)
            name = f"{name}.{p}"
        return name

    @property
    def fullname(self) -> str:
        return str(self.file_path.parent / self.name)

    def display_name(self, resolve: bool = False) -> str:
        return self.name if not resolve else self.fullname


class _GlobalSpecCache:
    """Simple cache for storing re-used data feeding the spec ID"""

    _key: dict[Path, Path] = {}
    """Maps the input file path to a key index (absolute path)"""

    _file_hash: dict[Path, bytes] = {}
    _repo_root: dict[Path, bytes] = {}
    _rel_repo: dict[Path, bytes] = {}
    _lock = threading.Lock()

    @classmethod
    def _compute_repo_root(cls, path: Path) -> Path:
        d = path.parent
        while d.parent != d:
            if (d / ".git").exists() or (d / ".repo").exists():
                root = d
                break
            d = d.parent
        else:
            root = d
        return root

    @classmethod
    def populate_cache(cls, path: Path) -> Path:
        try:
            return cls._key[path]
        except KeyError:
            pass

        key = path.absolute()
        h = hashlib.blake2b(digest_size=16, usedforsecurity=False)
        h.update(key.read_bytes())
        root = cls._compute_repo_root(key)
        rel = key.relative_to(root)

        with cls._lock:
            cls._repo_root[key] = str(root).encode()
            cls._rel_repo[key] = str(rel).encode()
            cls._file_hash[key] = h.hexdigest().encode()
            return cls._key.setdefault(path, key)

    @classmethod
    def file_hash(cls, path: Path) -> bytes:
        key = cls.populate_cache(path)
        return cls._file_hash[key]

    @classmethod
    def rel_repo(cls, path: Path) -> bytes:
        key = cls.populate_cache(path)
        return cls._rel_repo[key]


def build_id(*args: Any, **kwargs: Any) -> str:
    # Hasher is used to build ID
    float_fmt = "%.16e"
    hasher = hashlib.blake2b(usedforsecurity=False)
    for arg in args:
        if isinstance(arg, Path):
            hasher.update(_GlobalSpecCache.file_hash(arg))
            hasher.update(_GlobalSpecCache.rel_repo(arg))
        else:
            hasher.update(stringify(arg, float_fmt=float_fmt).encode())
    for key in sorted(kwargs):
        hasher.update(f"{key}={stringify(kwargs[key], float_fmt=float_fmt)}".encode())
    return hasher.hexdigest()


class UnresolvedDependenciesErrors(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))
