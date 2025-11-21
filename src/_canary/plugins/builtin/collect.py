# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path
from typing import Generator

from ... import config
from ...generator import AbstractTestGenerator
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import ScanPath

logger = logging.get_logger(__name__)


class Collector:
    errors: int = 0
    skip_dirs = ("__pycache__", ".git", ".svn")

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
                    if f := self.from_file(root, p):
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
        if root.is_file():
            try:
                if f := self.from_file(root.parent, root.name):
                    return [f]
            except Exception as e:
                raise ValueError(f"Failed to load {root}")

    def skip_dir(self, dirname: str) -> bool:
        if os.path.basename(dirname) in self.skip_dirs:
            return True
        if os.path.basename(dirname) == "TestResults":
            return True
        return False

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

    def from_directory(self, root: Path) -> Generator[AbstractTestGenerator, None, None]:
        # Cache repeated values
        generator_hook = config.pluginmanager.hook.canary_testcase_generator
        skip_dirs = self.skip_dirs  # tuple
        root_str = str(root)
        root_len = len(root_str) + 1  # for slicing to make relative paths fast

        for dirpath, dirnames, filenames in os.walk(root_str):
            # Fast skip-dir check
            basename = os.path.basename(dirpath)
            if basename in skip_dirs or basename == "TestResults":
                dirnames[:] = ()
                continue
            try:
                for name in filenames:
                    file_path = f"{dirpath}/{name}"
                    # Fast path → relative path (avoid os.path.relpath)
                    rel_path = file_path[root_len:]
                    try:
                        f = generator_hook(root=root, path=rel_path)
                    except Exception:
                        self.errors += 1
                        logger.exception(f"Failed to parse {rel_path}")
                        continue
                    if f:
                        yield f
                        if f.stop_recursion():
                            raise StopRecursion
            except StopRecursion:
                dirnames[:] = ()
                continue


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
