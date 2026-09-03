# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Intermediate representation (IR) for job specifications before dependency resolution.

:class:`JobSpecIR` is a mutable, pre-resolution form of a job specification.
It is produced by test generators (e.g. the PYT directive parser) and holds
all the raw field values needed to eventually construct a :class:`~_canary.jobspec.JobSpec`.
The key difference from ``JobSpec`` is that dependencies are still expressed as
:class:`DependencySelector` patterns rather than resolved spec references.

Once the full collection of ``JobSpecIR`` objects is known, dependency
resolution replaces each ``DependencySelector`` with matching spec IDs, and
:meth:`JobSpecIR.finalize` converts the IR into a ``JobSpec``.
"""

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
        """Validate ``expects`` to ensure it is a positive integer or one of ``'+', '?', '*'``."""
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
        """Return ``True`` if *spec* matches this selector's pattern.

        Checks the pattern against the spec's name, family, fullname,
        display name, resolved display name, and file path.  Glob wildcards
        are supported via :func:`fnmatch.fnmatchcase`.

        Args:
            spec: Any object with ``name``, ``family``, ``fullname``,
                ``display_name()``, and ``file_path`` attributes.
        """
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
        """Return a list of error strings if the match count *n* violates ``expects``.

        Args:
            n: Number of specs that matched this selector's pattern.

        Returns:
            An empty list if the count satisfies ``expects``, otherwise a list
            with one human-readable error message.
        """
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
    """Mutable intermediate representation of a job specification.

    Holds all raw field values as collected by a generator before dependency
    resolution has been performed.  The ``id`` is computed from the family
    name, file path, and non-runtime parameters immediately on construction so
    it remains stable across the collection phase.

    Call :meth:`finalize` to produce a fully resolved :class:`~_canary.jobspec.JobSpec`.

    Args:
        file_root: Absolute path to the collection root directory.
        file_path: Path to the test file, relative to *file_root*.
        id: Explicit spec ID override; auto-computed from content when ``None``.
        family: Test family name; defaults to the file stem.
        stdout: Filename for captured stdout (relative to the job work dir).
        stderr: Filename for captured stderr; ``None`` merges stderr into stdout.
        dependencies: List of :class:`DependencySelector` patterns or raw
            strings describing upstream jobs.
        parameters: Test parameters that become part of the job name/ID.
        meta_parameters: Extra parameters not included in the job name/ID.
        attributes: Arbitrary key/value metadata attached to the job.
        keywords: Filter keywords for ``-k`` selection.
        assets: Input files/directories to copy or link into the work dir.
        artifacts: Output files to collect from the work dir after the job.
        exclusive: When ``True``, the job must run alone on a node.
        timeout: Wall-clock timeout in seconds; ``-1`` infers from keywords.
        xstatus: Expected exit status; a non-zero value is treated as a pass.
        preload: Shell fragment sourced before the job command.
        modules: Environment modules to load.
        rcfiles: RC files to source before the job command.
        owners: List of owner identifiers for reporting.
        environment: Environment variable overrides (``None`` value unsets).
        command: Explicit command list; overrides the default test invocation.
        mask: Controls whether this spec is filtered out before execution.
        baseline: List of baseline copy/script actions for diff testing.
        view_path: Override for the view-relative path of the job result dir.
        exec_path: Override for the job execution directory.
    """

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
        """Append an artifact collection rule if it is not already present.

        Args:
            pattern: Glob pattern relative to the job work directory.
            when: Condition under which the artifact is collected.
        """
        a = Artifact(pattern=pattern, when=when)
        if a not in self.artifacts:
            self.artifacts.append(a)

    def set_attribute(self, name: str, value: Any) -> None:
        """Set a single metadata attribute on this spec.

        Args:
            name: Attribute key.
            value: Attribute value (must be JSON-serializable).
        """
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        """Set multiple metadata attributes at once.

        Args:
            **kwds: Key/value pairs to merge into :attr:`attributes`.
        """
        self.attributes.update(**kwds)

    def finalize(
        self, lookup: dict[str, "JobSpec"], resolved: Sequence[tuple[int, Sequence[str]]] = ()
    ) -> "JobSpec":
        """Construct the final :class:`~_canary.jobspec.JobSpec` from this IR.

        Args:
            lookup: Mapping of spec ID → ``JobSpec`` for all collected specs,
                used to resolve dependency references.
            resolved: Sequence of ``(dependency_index, [spec_id, ...])`` tuples
                produced by the dependency resolver.  Each entry maps the
                *n*-th :class:`DependencySelector` in :attr:`dependencies` to
                the list of matching spec IDs.

        Returns:
            A fully resolved, immutable :class:`~_canary.jobspec.JobSpec`.
        """
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
        """Expand dependency declarations against this spec's parameters.

        String templates in dependency patterns are substituted with the
        spec's parameter values using :class:`string.Template` safe
        substitution so missing keys are left as-is rather than raising.

        Args:
            args: Raw dependency strings or :class:`DependencySelector` objects.

        Returns:
            A list of :class:`DependencySelector` objects with parameter values
            substituted into their patterns.
        """
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
        """Short job name: family name plus sorted parameter key=value pairs."""
        name = self.family
        if self.parameters:
            parts = [f"{p}={stringify(self.parameters[p])}" for p in sorted(self.parameters.keys())]
            p = ".".join(parts)
            name = f"{name}.{p}"
        return name

    @property
    def fullname(self) -> str:
        """Full job name: parent directory path joined with :attr:`name`."""
        return str(self.file_path.parent / self.name)

    def display_name(self, resolve: bool = False) -> str:
        """Return the display name for this spec.

        Args:
            resolve: If ``True`` return :attr:`fullname` (includes directory
                prefix); otherwise return :attr:`name`.
        """
        return self.name if not resolve else self.fullname
