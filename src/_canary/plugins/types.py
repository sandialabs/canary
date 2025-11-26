# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import fnmatch
import os
from argparse import Namespace
from typing import TYPE_CHECKING
from typing import Any

from ..util import logging

if TYPE_CHECKING:
    from ..config.argparsing import Parser


logger = logging.get_logger(__name__)


class CanarySubcommand:
    """Canary subcommand used when defining a Canary subcommand plugin hook.

    Args:
      name: Subcommand name (e.g., ``canary my-subcommand``)
      description: Subcommand description, shown in ``canary --help``
      in_repo: Subcommand should be exected inside a test session folder
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized
      epilog: Epilog printed for ``canary my-subcommand --help``
      add_help: Whether to add subcommand to ``canary --help``

    """

    name: str
    description: str
    epilog: str | None = None
    add_help: bool = True

    def setup_parser(self, parser: "Parser") -> None:
        pass

    def execute(self, args: Namespace) -> int:
        raise NotImplementedError


class CanaryReporter:
    """Canary reporter class

    Args:
      type: Report type name (e.g., ``canary report my-report``)
      description: Subcommand description, shown in ``canary report --help``
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized
      multipage: Whether the report is a multi-page report

    """

    type: str
    description: str
    multipage: bool = False
    default_output: str = "report.ext"

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="action", metavar="subcommands")
        p = subparsers.add_parser("create", help=f"Create {self.type.upper()} report")
        if self.multipage:
            p.add_argument(
                "--dest", default="$canary_work_tree", help="Write reports to this directory"
            )
        else:
            p.add_argument(
                "-o", dest="output", help=f"Output file name [default: {self.default_output}]"
            )

    def create(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def not_implemented(self, **kwargs: Any) -> None:
        action = kwargs["action"]
        raise NotImplementedError(f"{self}: {action} method is not implemented")


class Result:
    def __init__(self, ok: bool | None = None, reason: str | None = None) -> None:
        if not ok:
            ok = not bool(reason)
        if not ok and not reason:
            raise ValueError(f"{self.__class__.__name__}(False) requires a reason")
        self.ok: bool = ok
        self.reason: str | None = reason

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        state = "ok" if self.ok else "fail"
        reason = f": {self.reason}" if self.reason else ""
        return f"<{self.__class__.__name__} {state}{reason}>"


class File(str):
    __slots__ = ("skip",)

    def __new__(cls, value):
        return str.__new__(cls, value)

    def __init__(self, value):
        self.skip = False


@dataclasses.dataclass
class Collector:
    file_patterns: list[str] = dataclasses.field(default_factory=list, init=False)
    skip_dirs: list[str] = dataclasses.field(default_factory=list, init=False)
    scanpaths: dict[str, list[str]] = dataclasses.field(default_factory=dict, init=False)
    files: dict[str, list[str]] = dataclasses.field(default_factory=dict, init=False)

    def add_file_patterns(self, *patterns: str) -> None:
        for pattern in patterns:
            if pattern not in self.file_patterns:
                self.file_patterns.append(pattern)

    def add_skip_dirs(self, *dirs: str) -> None:
        for dir in dirs:
            if dir not in self.skip_dirs:
                self.skip_dirs.append(dir)

    def add_scanpaths(self, root: str, paths: list[str] | None = None) -> None:
        existing = set(self.scanpaths.setdefault(root, []))
        if paths:
            existing.update(paths)
        self.scanpaths[root] = sorted(existing)

    def add_files_to_root(self, root: str, paths: list[str]) -> None:
        existing: set[str] = set(self.files.setdefault(root, []))
        for path in paths:
            relpath = os.path.relpath(path, root) if os.path.isabs(path) else path
            if not os.path.exists(os.path.join(root, relpath)):
                logger.warning(f"{root}/{relpath}: path does not exist")
            else:
                existing.add(relpath)
        self.files[root] = sorted(existing)

    def is_testfile(self, f: str) -> bool:
        for pattern in self.file_patterns:
            if fnmatch.fnmatchcase(f, pattern):
                return True
        return False
