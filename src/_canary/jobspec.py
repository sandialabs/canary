# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import hashlib
import itertools
import threading
from functools import cached_property
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import MutableSequence

from .util import logging
from .util.string import stringify

if TYPE_CHECKING:
    from .status import Status

logger = logging.get_logger(__name__)
select_sygil = "/"


@dataclasses.dataclass
class Asset:
    src: Path
    dst: str | None
    action: Literal["copy", "link", "none"]

    def __serialize__(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "action": self.action}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Asset":
        src = Path(d.pop("src"))
        return cls(src=src, **d)


@dataclasses.dataclass(frozen=True, slots=True)
class BaselineCopyAction:
    src: Path
    dst: str
    kind: Literal["copy"] = dataclasses.field(default="copy", init=False)

    def __serialize__(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst}

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "BaselineCopyAction":
        return cls(src=Path(d["src"]), dst=d["dst"])


@dataclasses.dataclass(frozen=True, slots=True)
class BaselineScriptAction:
    script: list[str] = dataclasses.field(default_factory=list)
    kind: Literal["script"] = dataclasses.field(default="script", init=False)

    def __post_init__(self) -> None:
        if not self.script:
            raise TypeError("BaselineScriptAction requires non-empty script")

    def __serialize__(self) -> dict[str, Any]:
        return {"script": self.script}

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "BaselineScriptAction":
        return cls(script=list(d["script"]))


BaselineAction = BaselineCopyAction | BaselineScriptAction


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


NULL_PATH = Path("\0")


@dataclasses.dataclass
class JobSpec:
    # The search path containing the generated spec; typically the some version-control root
    file_root: Path
    # The path to the test file relative to `file_root`
    file_path: Path
    id: str = ""
    family: str = ""
    stdout: str = "canary-out.txt"
    stderr: str | None = None  # combine stdout/stderr by default
    dependencies: MutableSequence[SpecDependency] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    keywords: list[str] = dataclasses.field(default_factory=list)
    assets: list[Asset] = dataclasses.field(default_factory=list)
    baseline: list[BaselineAction] = dataclasses.field(default_factory=list)
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

    exec_path: Path = dataclasses.field(default=NULL_PATH)
    view_path: Path = dataclasses.field(default=NULL_PATH)

    def __post_init__(self) -> None:
        self.family = self.family or self.file.stem
        if not self.id:
            kwds = self.parameters | self.meta_parameters
            kwds.pop("runtime", None)
            self.id = build_spec_id(self.family, self.file_root / self.file_path, **kwds)
        if self.exec_path == NULL_PATH:
            self.exec_path = self.file_path.parent / self.name
        self.exec_path = Path(self.exec_path)
        if self.view_path == NULL_PATH:
            self.view_path = self.file_path.parent / self.name
        self.view_path = Path(self.view_path)

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
            "mask": self.mask,
            "exec_path": self.exec_path,
            "view_path": self.view_path,
        }

    @classmethod
    def __deserialize__(cls, d: dict) -> "JobSpec":
        root = Path(d.pop("file_root"))
        path = Path(d.pop("file_path"))
        exec_path = Path(d.pop("exec_path"))
        view_path = Path(d.pop("view_path"))
        return cls(file_root=root, file_path=path, exec_path=exec_path, view_path=view_path, **d)

    def add_artifact(
        self, pattern: str, when: Literal["always", "never", "on_failure", "on_success"] = "always"
    ) -> None:
        self.artifacts.append(Artifact(pattern=pattern, when=when))

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

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_attributes(self, **kwds: Any) -> None:
        self.attributes.update(**kwds)

    def matches(self, arg: str, *, fuzzy: bool = False) -> bool:
        s = arg.strip()
        if not s:
            return False

        # Legacy: leading "/" indicates an ID prefix, but "/" is also a Unix root anchor.
        # We therefore:
        #   1) always attempt ID-prefix matching (with "/" stripped if present)
        #   2) only treat paths as matching if they resolve to *this* spec's file
        id_query = s[1:] if s.startswith(select_sygil) else s
        if id_query and self.id.startswith(id_query):
            return True

        # If arg looks like a path, allow matching by file identity
        # - absolute paths (Unix "/" anchor included)
        # - any string containing a path separator
        looks_like_path = (Path(s).is_absolute()) or ("/" in s) or ("\\" in s)
        if looks_like_path:
            p = Path(s)
            try:
                if p.exists() and p.resolve() == self.file.resolve():
                    return True
            except OSError:
                pass
            try:
                pr = self.file_root / p
                if pr.exists() and pr.resolve() == self.file.resolve():
                    return True
            except OSError:
                pass

        if s == self.fullname:
            return True

        if not fuzzy:
            return False

        if s == self.name:
            return True

        if s == self.family:
            return True

        # Suffix match on the spec file path (normalize separators for cross-platform use)
        s_posix = s.replace("\\", "/")
        if "/" in s_posix and self.file.as_posix().endswith(s_posix):
            return True

        return False


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
        h = hashlib.sha256()
        h.update(key.read_bytes())
        digest = h.digest()[:16]
        root = cls._compute_repo_root(key)
        rel = key.relative_to(root)

        with cls._lock:
            cls._repo_root[key] = str(root).encode()
            cls._rel_repo[key] = str(rel).encode()
            cls._file_hash[key] = digest.hex().encode()
            return cls._key.setdefault(path, key)

    @classmethod
    def file_hash(cls, path: Path) -> bytes:
        key = cls.populate_cache(path)
        return cls._file_hash[key]

    @classmethod
    def rel_repo(cls, path: Path) -> bytes:
        key = cls.populate_cache(path)
        return cls._rel_repo[key]


def build_spec_id(*args: Any, **kwargs: Any) -> str:
    # Hasher is used to build ID
    float_fmt = "%.16e"
    hasher = hashlib.sha256()
    for arg in args:
        if isinstance(arg, Path):
            hasher.update(_GlobalSpecCache.file_hash(arg))
            hasher.update(_GlobalSpecCache.rel_repo(arg))
        else:
            hasher.update(stringify(arg, float_fmt=float_fmt).encode())
    for key in sorted(kwargs):
        hasher.update(f"{key}={stringify(kwargs[key], float_fmt=float_fmt)}".encode())
    return hasher.hexdigest()
