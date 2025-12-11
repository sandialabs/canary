# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

from .util import logging
from .util.filesystem import force_remove

if TYPE_CHECKING:
    pass

logger = logging.get_logger(__name__)

key_type = tuple[str, ...] | str
index_type = tuple[int, ...] | int


@dataclasses.dataclass
class ExecutionSpace:
    root: Path
    path: Path
    session: str | None = None

    def __str__(self) -> str:
        return str(self.dir)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.path = Path(self.path)

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "ExecutionSpace":
        return cls(root=Path(state["root"]), path=Path(state["path"]), session=state["session"])

    @property
    def dir(self) -> Path:
        return self.root / self.path

    def create(self, exist_ok: bool = False) -> None:
        self.dir.mkdir(parents=True, exist_ok=exist_ok)

    def remove(self, missing_ok: bool = False) -> None:
        if self.exists():
            force_remove(self.dir)
        elif not missing_ok:
            raise FileNotFoundError(self.dir)

    @contextmanager
    def enter(self) -> Generator[None, None, None]:
        current_cwd = Path.cwd()
        try:
            os.chdir(self.dir)
            yield
        finally:
            os.chdir(current_cwd)

    @contextmanager
    def openfile(self, name: Path | str, mode: str = "r") -> Generator[IO[Any], None, None]:
        try:
            fh = open(self.dir / name, mode=mode)
            yield fh
        finally:
            fh.close()

    def exists(self) -> bool:
        return self.dir.exists()

    def touch(self, name: Path | str, exist_ok: bool = False) -> None:
        (self.dir / name).touch(exist_ok=exist_ok)

    def unlink(self, name: Path | str, missing_ok: bool = False) -> None:
        (self.dir / name).unlink(missing_ok=missing_ok)

    def copy(self, src: Path, dst: Path | str | None = None) -> None:
        """Copy the file at ``src`` to this workspace with name ``dst``"""
        dest: Path = Path(dst or src.name)
        (self.dir / dest.name).unlink(missing_ok=True)
        shutil.copy(str(src), str(self.dir / dest.name))

    def link(self, src: Path, dst: Path | str | None = None) -> None:
        """Symlink the file at ``src`` to this workspace with name ``dst``"""
        dest: Path = Path(dst or src.name)
        (self.dir / dest.name).unlink(missing_ok=True)
        (self.dir / dest.name).symlink_to(src)

    def joinpath(self, *parts: Path | str) -> Path:
        f = self.dir
        for part in parts:
            f /= part
        return f
