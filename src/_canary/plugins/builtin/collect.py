# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import fnmatch
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Generator

from ... import config
from ...generator import AbstractTestGenerator
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import File
from ..types import ScanPath

logger = logging.get_logger(__name__)


class Collector:
    errors: int = 0

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
        patterns: list[str] = config.pluginmanager.hook.canary_collect_file_patterns()
        files = git_ls(root, patterns) if type == "git" else repo_ls(root)

        files = filter_files(files)
        return self.create_generators_from_files(root, files)

    def from_directory(self, root: Path) -> list[AbstractTestGenerator]:
        # Cache repeated values
        skip_dirs = config.pluginmanager.hook.canary_collect_skip_dirs()
        patterns = config.pluginmanager.hook.canary_collect_file_patterns()
        root_str = str(root)
        root_len = len(root_str) + 1  # for slicing to make relative paths fast

        files: list[str] = []
        for dirname, dirs, names in os.walk(root_str):
            # Fast skip-dir check
            basename = os.path.basename(dirname)
            if basename in skip_dirs:
                dirs[:] = ()
                continue
            for name in names:
                for pattern in patterns:
                    if fnmatch.fnmatchcase(name, pattern):
                        file_path = f"{dirname}/{name}"
                        # Fast path → relative path (avoid os.path.relpath)
                        rel_path = file_path[root_len:]
                        files.append(rel_path)
                        break

        files = filter_files(files)
        return self.create_generators_from_files(root, files)

    def create_generators_from_files(self, root, files):
        all_files = [(root, file) for file in files]
        with ProcessPoolExecutor() as ex:
            futures = [ex.submit(generate_one, arg) for arg in all_files]
            results = [f.result() for f in futures]
        generators: list[AbstractTestGenerator] = []
        for success, result in results:
            if not success:
                self.errors += 1
            elif result is not None:
                generators.append(result)
        return generators


def filter_files(files: list[str]) -> list[str]:
    file_objs = [File(f) for f in files]
    config.pluginmanager.hook.canary_collect_filter_files(files=file_objs)
    return [str(file) for file in file_objs if not file.skip]


@hookimpl(wrapper=True)
def canary_collect_file_patterns() -> Generator[None, None, list[str]]:
    patterns = []
    result = yield
    for items in result:
        patterns.extend(items)
    return patterns


@hookimpl(wrapper=True)
def canary_collect_skip_dirs() -> Generator[None, None, list[str]]:
    default = {"__pycache__", ".git", ".svn", ".hg", config.get("view") or "TestResults"}
    result = yield
    for items in result:
        default.update(items)
    return sorted(default)


def git_ls(root: str, patterns: list[str]) -> list[str]:
    gitified_patterns = [f"**/{p}" for p in patterns]
    args = [
        "git",
        "-C",
        root,
        "ls-files",
        "--recurse-submodules",
        "--",
        *gitified_patterns,
    ]
    cp = subprocess.run(args, capture_output=True, text=True)
    return [f.strip() for f in cp.stdout.split("\n") if f.split()]


def repo_ls(root: str) -> list[str]:
    args = ["repo", "-c", "git ls-files --recurse-submodules"]
    with working_dir(root):
        cp = subprocess.run(args, capture_output=True, text=True)
    return [f.strip() for f in cp.stdout.split("\n") if f.split()]


def generate_one(args) -> tuple[bool, AbstractTestGenerator | None]:
    generator_hook = config.pluginmanager.hook.canary_testcase_generator
    root, f = args
    try:
        gen = generator_hook(root=root, path=f)
        return True, gen
    except Exception:
        logger.exception(f"Failed to parse test from {root}/{f}")
        return False, None


class StopRecursion(Exception):
    pass
