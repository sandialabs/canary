# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import itertools
from functools import cached_property
from functools import lru_cache
from pathlib import Path
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import MutableSequence

from .util import json_helper as json
from .util import logging
from .util.string import stringify

if TYPE_CHECKING:
    from .status import Status

logger = logging.get_logger(__name__)
select_sygil = "/"


@dataclasses.dataclass
class Asset:
    src: Path
    dst: str
    action: Literal["copy", "link", "none"]

    def __serialize__(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "action": self.action}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Asset":
        src = Path(d.pop("src"))
        return cls(src=src, **d)


@dataclasses.dataclass(frozen=True)
class Artifact:
    pattern: str
    when: Literal["always", "never", "on_failure", "on_success"] = "always"

    def active(self, status: "Status") -> bool:
        from .status import Category

        if self.when == "never":
            return False
        elif self.when == "always":
            return True
        elif self.when == "on_failure":
            return status.category is Category.FAIL
        elif self.when == "on_success":
            return status.category is Category.PASS
        return True

    def __serialize__(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "when": self.when}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Artifact":
        return cls(**d)


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

    def __serialize__(self) -> dict[str, Any]:
        return {"value": self.value, "reason": self.reason}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Mask":
        return cls(**d)

    @classmethod
    def masked(cls, reason: str) -> "Mask":
        return cls(True, reason)

    @classmethod
    def unmasked(cls) -> "Mask":
        return cls(False, None)


@dataclasses.dataclass(slots=True)
class SpecDependency:
    spec: "JobSpec"
    when: str = "on_success"

    def __serialize__(self) -> dict[str, Any]:
        return {"spec": self.spec, "when": self.when}

    @classmethod
    def __deserialize__(cls, d: dict) -> "SpecDependency":
        return cls(**d)


@dataclasses.dataclass
class JobSpec:
    # The search path containing the generated spec; typically the some version-control root
    file_root: Path
    # The path to the test file relative to `file_root`
    file_path: Path
    id: str
    family: str = ""
    stdout: str = "canary-out.txt"
    stderr: str | None = None  # combine stdout/stderr by default
    dependencies: MutableSequence["SpecDependency"] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    keywords: list[str] = dataclasses.field(default_factory=list)
    assets: list["Asset"] = dataclasses.field(default_factory=list)
    baseline: list[dict] = dataclasses.field(default_factory=list)
    artifacts: list[Artifact] = dataclasses.field(default_factory=list)
    exclusive: bool = False
    timeout: float = -1.0
    xstatus: int = 0
    preload: str | None = None
    modules: list[str] | None = None
    rcfiles: list[str] | None = None
    owners: list[str] | None = None
    environment: dict[str, str | None] = dataclasses.field(default_factory=dict)
    meta_parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    command: list[str] = dataclasses.field(default_factory=list)
    mask: Mask = dataclasses.field(default_factory=Mask.unmasked)
    exec_path: str | None = None
    view_path: str | None = None

    def __post_init__(self) -> None:
        self.family = self.family or self.file.stem

    def __hash__(self) -> int:
        return hash(self.id)

    def __serialize__(self) -> dict[str, Any]:
        return {
            "file_root": self.file_root,
            "file_path": self.file_path,
            "id": self.id,
            "family": self.family,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "dependencies": list(self.dependencies),
            "parameters": self.parameters,
            "attributes": self.attributes,
            "keywords": self.keywords,
            "assets": self.assets,
            "baseline": self.baseline,
            "artifacts": self.artifacts,
            "exclusive": self.exclusive,
            "timeout": self.timeout,
            "xstatus": self.xstatus,
            "preload": self.preload,
            "modules": self.modules,
            "rcfiles": self.rcfiles,
            "owners": self.owners,
            "environment": self.environment,
            "meta_parameters": self.meta_parameters,
            "command": self.command,
            "mask": self.mask,  # keep as Mask object
            "exec_path": self.exec_path,
            "view_path": self.view_path,
        }

    @classmethod
    def __deserialize__(cls, d: dict) -> "JobSpec":
        root = Path(d.pop("file_root"))
        path = Path(d.pop("file_path"))
        return cls(file_root=root, file_path=path, **d)

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def dump(self, file: IO[Any], **kwargs: Any) -> None:
        json.dump(self.asdict(), file, **kwargs)

    def dumps(self, **kwargs: Any) -> Any:
        return json.dumps(self.asdict(), **kwargs)

    def add_artifact(
        self, pattern: str, when: Literal["always", "never", "on_failure", "on_success"] = "always"
    ) -> None:
        self.artifacts.append(Artifact(pattern=pattern, when=when))

    @classmethod
    def from_dict(cls, d: dict, lookup: dict[str, "JobSpec"]) -> "JobSpec":
        state = dict(d)
        mask = state.pop("mask", None)
        if mask:
            state["mask"] = Mask(mask["value"], mask["reason"])
        state["file_root"] = Path(state.pop("file_root"))
        state["file_path"] = Path(state.pop("file_path"))
        dependencies = [lookup[dep["id"]] for dep in state["dependencies"]]
        state["dependencies"] = dependencies
        assets = [
            Asset(src=Path(a["src"]), dst=a["dst"], action=a["action"]) for a in state["assets"]
        ]
        state["assets"] = assets
        state["artifacts"] = [Artifact(**x) for x in state["artifacts"]]
        self = cls(**d)  # ty: ignore[missing-argument]
        return self

    @cached_property
    def file(self) -> Path:
        """Path to the test specification file"""
        return self.file_root / self.file_path

    @property
    def mtime(self) -> float:
        return self.file.stat().st_mtime

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

    @property
    def viewpath(self) -> str:
        if p := self.attributes.get("viewpath"):
            return p
        return self.execpath

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
        return {self.name, self.family, str(self.file)}

    def matches(self, arg: str) -> bool:
        if arg.startswith(select_sygil) and not Path(arg).exists():
            arg = arg[1:]
        if self.display_name() == arg:
            return True
        if self.name == arg:
            return True
        return False

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        self.attributes.update(**kwds)
