# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import fnmatch
import shlex
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal
from typing import Sequence

from .jobspec import NULL_PATH
from .jobspec import Artifact
from .jobspec import Asset
from .jobspec import BaselineAction
from .jobspec import JobSpec
from .jobspec import Mask
from .jobspec import SpecDependency
from .jobspec import build_spec_id
from .jobspec import default_timeout
from .util import logging
from .util.string import stringify

FileResourceT = dict[Literal["copy", "link", "none"], list[tuple[str, str | None]]]
logger = logging.get_logger(__name__)


@dataclass
class DependencySelector:
    """String representation of test dependencies

    Dependency resolution is performed after job discovery.  The ``DependencySelector``
    object holds information needed to perform the resolution.

    Args:
      value: The dependency name or glob pattern.
      expect: For glob patterns, how many dependencies are expected to be found
      result: The job will run if the dependency exits with this status.  Usually ``success``

    """

    pattern: str
    expects: str | int = "+"
    when: str = "on_success"

    def __post_init__(self):
        expects = self.expects
        if not isinstance(expects, (str, int)):
            raise TypeError(f"DependencySelector.expects: invalid type {type(expects).__name__!r}")
        if isinstance(expects, str):
            choices = {"+", "?", "*"}
            if expects not in choices:
                s = ", ".join(sorted(choices))
                msg = f"DependencySelector.expect: invalid choice: {expects!r} (choose from {s})"
                raise TypeError(msg)
        elif expects <= 0:
            raise ValueError(f"DependencySelector.expect: invalid value: {expects!r} (must be > 0)")

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

    def verify(self, n: int) -> list[str]:
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
        dependencies: list[DependencySelector] | None = None,
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
        mask: Mask = Mask.unmasked(),
        baseline: list[BaselineAction] | None = None,
        view_path: str | None = None,
        exec_path: str | None = None,
    ):
        self.file_root: Path = Path(file_root)
        self.file_path: Path = Path(file_path)
        self.file = self.file_root / self.file_path
        self.family: str = family or self.file.stem
        self.parameters: dict[str, Any] = dict(parameters or {})
        self.meta_parameters: dict[str, Any] = dict(meta_parameters or {})
        duplicate_parameter_keys = set(self.parameters) & set(self.meta_parameters)
        if duplicate_parameter_keys:
            keys = ", ".join(sorted(duplicate_parameter_keys))
            raise ValueError(
                "JobSpecIR received duplicate key(s) in parameters and meta_parameters: "
                f"{keys}. A key may appear in only one of these dictionaries."
            )
        self.stdout: str = stdout
        self.stderr: str | None = stderr
        self.dependencies: list[DependencySelector] = self.build_dependencies(dependencies or [])
        self.attributes: dict[str, Any] = attributes or {}
        self.keywords: list[str] = keywords or []
        self.assets: list[Asset] = assets or []
        self.assets = self.assets or []
        self.artifacts: list[Artifact] = artifacts or []
        self.exclusive = exclusive
        if timeout < 0:
            timeout = default_timeout(self.keywords)
        self.timeout: float = timeout
        if "runtime" not in self.meta_parameters:
            self.meta_parameters["runtime"] = self.timeout
        self.xstatus: int = xstatus
        self.preload: str | None = preload
        self.modules: list[str] | None = modules
        self.rcfiles: list[str] | None = rcfiles
        self.owners: list[str] | None = owners
        self.environment: dict[str, str | None] = environment or {}
        self.command = command or []
        self.mask = mask
        self.baseline = baseline or []
        self.exec_path: str | None = exec_path
        self.view_path: str | None = view_path

        if id is None:
            kwds = self.parameters | self.meta_parameters
            kwds.pop("runtime")
            id = build_spec_id(self.family, self.file_root / self.file_path, **kwds)
        self.id: str = id

    def __hash__(self) -> int:
        return hash(self.id)

    def add_artifact(
        self, pattern: str, when: Literal["always", "never", "on_failure", "on_success"] = "always"
    ) -> None:
        a = Artifact(pattern=pattern, when=when)
        if a not in self.artifacts:
            self.artifacts.append(a)

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        self.attributes.update(**kwds)

    def finalize(
        self, lookup: dict[str, "JobSpec"], resolved: Sequence[tuple[int, Sequence[str]]] = ()
    ) -> "JobSpec":
        deps: list[SpecDependency] = []
        for dp_index, ids in resolved:
            dp = self.dependencies[dp_index]
            for dep_id in ids:
                deps.append(SpecDependency(spec=lookup[dep_id], when=dp.when))

        return JobSpec(
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
            exec_path=NULL_PATH if not self.exec_path else Path(self.exec_path),
            view_path=NULL_PATH if not self.view_path else Path(self.view_path),
        )

    def build_dependencies(
        self, args: Sequence[str | DependencySelector]
    ) -> list[DependencySelector]:
        dependency_specs: list[DependencySelector] = []
        parameters: dict[str, str] = {}
        for key, val in self.parameters.items():
            parameters[key] = stringify(val)
        for arg in args:
            if isinstance(arg, DependencySelector):
                t = string.Template(arg.pattern)
                pattern = t.safe_substitute(**parameters)
                d = DependencySelector(pattern=pattern, expects=arg.expects, when=arg.when)
                dependency_specs.append(d)
            else:
                t = string.Template(arg)
                pattern = t.safe_substitute(**parameters)
                dep_pattern = DependencySelector(pattern=pattern)
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
