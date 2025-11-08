# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path
from typing import Generator

from ... import config
from ...generator import AbstractTestGenerator
from ..hookspec import hookimpl
from ..types import ScanPath
from ...util import logging
from ...util.filesystem import working_dir

logger = logging.get_logger(__name__)


class Collector:
    errors: int = 0
    skip = ("__pycache__", ".git", ".svn")

    @hookimpl(specname="canary_collect_generators")
    def collect_from_directory(self, scan_path: ScanPath) -> list[AbstractTestGenerator] | None:
        root = Path(scan_path.root)
        if not root.is_dir():
            return None
        self.errors = 0
        generators: list[AbstractTestGenerator] = []
        if not scan_path.paths:
            generators.extend(self.from_directory(root))
        else:
            for p in scan_path.paths:
                if (root / p).is_file():
                    if f := self.collect_file(root, p):
                        generators.append(f)
                elif (root / p).is_dir():
                    generators.extend(self.from_directory(root / p))
                else:
                    logger.warning(f"{root / p}: path does not exist")
        if self.errors:
            raise ValueError("Stopping due to previous errors")
        return generators

    @hookimpl(specname="canary_collect_generators")
    def collect_from_vc(self, scan_path: ScanPath) -> list[AbstractTestGenerator] | None:
        if scan_path.root.startswith(("git@", "repo@")):
            generators = list(self.from_version_control(scan_path.root))
            if self.errors:
                raise ValueError("Stopping due to previous errors")
            return generators

    @hookimpl(specname="canary_collect_generators")
    def collect_from_file(self, scan_path: ScanPath) -> list[AbstractTestGenerator] | None:
        root = Path(scan_path.root)
        if not root.is_file():
            try:
                if f := self.from_file(root.parent, root.name):
                    return [f]
            except Exception as e:
                raise ValueError(f"Failed to load {root}")

    def from_directory(self, root: Path) -> Generator[AbstractTestGenerator, None, None]:
        hk = config.pluginmanager.hook
        for dir, dirs, files in os.walk(str(root)):
            try:
                if dir.startswith(self.skip):
                    del dirs[:]
                    continue
                for name in files:
                    try:
                        file = os.path.join(dir, name)
                        path = os.path.relpath(file, root)
                        if f := hk.canary_testcase_generator(root=root, path=path):
                            yield f
                    except Exception as e:
                        self.errors += 1
                        logger.exception(f"Failed to parse {path}")
                    else:
                        if f and f.stop_recursion():
                            raise StopRecursion
            except StopRecursion:
                del dirs[:]
                continue
        return

    def from_file(self, root: Path, path: Path) -> AbstractTestGenerator | None:
        hk = config.pluginmanager.hook
        try:
            if f := hk.canary_testcase_generator(root=str(root), path=str(path)):
                return f
        except Exception:
            self.errors += 1
            logger.exception(f"Failed to parse {path}")
        return

    def from_version_control(self, root: str) -> Generator[AbstractTestGenerator, None, None]:
        """Find files in version control repository (only git supported)"""
        type, _, root = root.partition("@")
        if type not in ("git", "repo"):
            raise TypeError("Unknown vc type {type!r}, choose from git, repo")
        hk = config.pluginmanager.hook
        files = git_ls(root) if type == "git" else repo_ls(root)
        with working_dir(root):
            for file in files:
                try:
                    if f := hk.canary_testcase_generator(root=root, path=file):
                        yield f
                except Exception as e:
                    self.errors += 1
                    logger.exception(f"Failed to parse {root}/{file}")


def git_ls(root: str) -> list[str]:
    args = ["git", "ls-files", "--recurse-submodules"]
    with working_dir(root):
        cp = subprocess.run(args, capture_output=True, text=True)
    return [f.strip() for f in cp.stdout.split("\n") if f.split()]


def repo_ls(root: str) -> list[str]:
    args = ["repo", "-c", "git ls-files --recurse-submodules"]
    with working_dir(root):
        cp = subprocess.run(args, capture_output=True, text=True)
    return [f.strip() for f in cp.stdout.split("\n") if f.split()]


class StopRecursion(Exception):
    pass
