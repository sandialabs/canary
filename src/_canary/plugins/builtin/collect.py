# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import fnmatch
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING
from typing import Generator

from ... import config
from ...generator import AbstractTestGenerator
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import File

if TYPE_CHECKING:
    from ...generator import AbstractTestGenerator

logger = logging.get_logger(__name__)


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


class Collector:
    def __init__(self) -> None:
        self._patterns: list[str] | None = None
        self._skip_dirs: list[str] | None = None

    def file_patterns(self) -> list[str]:
        if self._patterns is None:
            self._patterns = config.pluginmanager.hook.canary_collect_file_patterns()
        assert self._patterns is not None
        return self._patterns

    def skip_dirs(self) -> list[str]:
        if self._skip_dirs is None:
            self._skip_dirs = config.pluginmanager.hook.canary_collect_skip_dirs()
        assert self._skip_dirs is not None
        return self._skip_dirs

    def is_testfile(self, f: str) -> bool:
        for pattern in self.file_patterns():
            if fnmatch.fnmatchcase(f, pattern):
                return True
        return False

    @hookimpl(wrapper=True)
    def canary_collect(
        self, root: str, paths: list[str]
    ) -> Generator[None, None, list["AbstractTestGenerator"]]:
        results = yield
        files: list[File] = []
        for result in results:
            for f in result or []:
                if not os.path.exists(f):
                    logger.warning(f"{f}: file does not exist")
                else:
                    files.append(File(f))
        config.pluginmanager.hook.canary_collect_modifyitems(files=files)
        generators = self._create_generators_from_files(root, [f for f in files if not f.skip])
        return generators

    def _create_generators_from_files(
        self, root: str, files: list[File]
    ) -> list["AbstractTestGenerator"]:
        errors = 0
        fs_root = root if "@" not in root else root.partition("@")[-1]
        root_len = len(fs_root) + 1  # for slicing to make relative paths fast
        all_files = [(fs_root, file[root_len:]) for file in files]
        with ProcessPoolExecutor() as ex:
            futures = [ex.submit(generate_one, arg) for arg in all_files]
            results = [f.result() for f in futures]
        generators: list[AbstractTestGenerator] = []
        for success, result in results:
            if not success:
                errors += 1
            elif result is not None:
                generators.append(result)
        if errors:
            raise ValueError("Stopping due to previous errors")
        return generators

    @hookimpl(specname="canary_collect")
    def collect_from_directory(self, root: str, paths: list[str]) -> list[str] | None:
        if not os.path.isdir(root):
            return None
        elif not paths:
            return self._from_directory(root=root)
        files: list[str] = []
        for p in paths:
            path = os.path.join(root, p)
            if os.path.isfile(path) and self.is_testfile(p):
                files.append(path)
            elif os.path.isdir(path):
                files.extend(self._from_directory(path))
            else:
                logger.warning(f"{root}/{p}: path does not exist")
        return files

    @hookimpl(specname="canary_collect")
    def collect_from_vc(self, root: str, paths: list[str]) -> list[str] | None:
        if not root.startswith(("git@", "repo@")):
            return None
        # FIXME: what if paths
        return self._from_version_control(root)

    @hookimpl(specname="canary_collect")
    def collect_from_file(self, root: str, paths: list[str]) -> list[str] | None:
        if not paths and os.path.isfile(root) and self.is_testfile(root):
            return [root]

    def _from_version_control(self, root: str) -> list[str]:
        """Find files in version control repository (only git supported)"""
        type, _, root = root.partition("@")
        if type not in ("git", "repo"):
            raise TypeError("Unknown vc type {type!r}, choose from git, repo")
        if type == "git":
            return git_ls(root, self.file_patterns())
        else:
            return repo_ls(root, self.file_patterns())

    def _from_directory(self, root: str) -> list[str]:
        # Cache repeated values
        files: list[str] = []
        for dirname, dirs, names in os.walk(root):
            # Fast skip-dir check
            basename = os.path.basename(dirname)
            if basename in self.skip_dirs():
                dirs[:] = ()
                continue
            for name in names:
                if self.is_testfile(name):
                    files.append(os.path.join(dirname, name))
        return files


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
    return [os.path.join(root, f.strip()) for f in cp.stdout.split("\n") if f.split()]


def repo_ls(root: str, patterns: list[str]) -> list[str]:
    files: list[str] = []
    with working_dir(root):
        cp = subprocess.run(["repo", "list"], capture_output=True, text=True)
        paths = [line.split(":")[0].strip() for line in cp.stdout.splitlines()]
        for p in paths:
            proj_files = git_ls(p, patterns)
            if p == ".":
                files.extend(os.path.join(root, proj_files))
            else:
                files.extend([os.path.join(root, p, f) for f in proj_files])
    return files


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
