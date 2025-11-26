# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING
from typing import Callable

from ... import config
from ...generator import AbstractTestGenerator
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import Collector

if TYPE_CHECKING:
    from ...generator import AbstractTestGenerator

logger = logging.get_logger(__name__)


@hookimpl(tryfirst=True)
def canary_collect(collector: Collector) -> list["AbstractTestGenerator"]:
    config.pluginmanager.hook.canary_collectstart(collector=collector)
    config.pluginmanager.hook.canary_collectitems(collector=collector)
    config.pluginmanager.hook.canary_collect_modifyitems(collector=collector)
    return generate_test_generators(collector)


@hookimpl
def canary_collectstart(collector: Collector) -> None:
    dirs = ("__pycache__", ".git", ".svn", ".hg", config.get("view") or "TestResults")
    collector.add_skip_dirs(*dirs)


def generate_test_generators(collector: Collector) -> list["AbstractTestGenerator"]:
    errors = 0
    generators: list[AbstractTestGenerator] = []
    for root, paths in collector.files.items():
        all_paths = [(root, path) for path in paths]
        with ProcessPoolExecutor() as ex:
            futures = [ex.submit(generate_one, arg) for arg in all_paths]
            results = [f.result() for f in futures]
        for success, result in results:
            if not success:
                errors += 1
            elif result is not None:
                generators.append(result)
    if errors:
        raise ValueError("Stopping due to previous errors")
    return generators


@hookimpl(specname="canary_collectitems")
def collect_from_directory(collector: Collector) -> None:
    for root, paths in collector.scanpaths.items():
        files: list[str] = []
        if not os.path.isdir(root):
            continue
        elif not paths:
            files.extend(_from_directory(root, collector.skip_dirs, collector.is_testfile))
        else:
            for p in paths:
                path = os.path.join(root, p)
                if os.path.isfile(path) and collector.is_testfile(p):
                    files.append(path)
                elif os.path.isdir(path):
                    files.extend(_from_directory(path, collector.skip_dirs, collector.is_testfile))
                else:
                    logger.warning(f"{root}/{p}: path does not exist")
        collector.add_files_to_root(root, files)


@hookimpl(specname="canary_collectitems")
def collect_from_vc(collector: Collector) -> None:
    for root in collector.scanpaths:
        if not root.startswith(("git@", "repo@")):
            continue
        type, _, vcroot = root.partition("@")
        files = _from_version_control(type, vcroot, collector.file_patterns)
        collector.add_files_to_root(vcroot, files)


@hookimpl(specname="canary_collectitems")
def collect_from_file(collector: Collector) -> None:
    for root, paths in collector.scanpaths.items():
        if not paths and os.path.isfile(root) and collector.is_testfile(root):
            dirname, basename = os.path.split(root)
            collector.add_files_to_root(dirname, [basename])


def _from_version_control(type: str, root: str, file_patterns: list[str]) -> list[str]:
    """Find files in version control repository (only git supported)"""
    if type not in ("git", "repo"):
        raise TypeError("Unknown vc type {type!r}, choose from git, repo")
    if type == "git":
        return git_ls(root, file_patterns)
    else:
        return repo_ls(root, file_patterns)


def _from_directory(
    root: str, skip_dirs: list[str], is_testfile: Callable[[str], bool]
) -> list[str]:
    # Cache repeated values
    files: list[str] = []
    for dirname, dirs, names in os.walk(root):
        # Fast skip-dir check
        basename = os.path.basename(dirname)
        if basename in skip_dirs:
            dirs[:] = ()
            continue
        for name in names:
            if is_testfile(name):
                f = os.path.join(dirname, name)
                files.append(str(os.path.relpath(f, root)))
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
    return [f.strip() for f in cp.stdout.split("\n") if f.split()]


def repo_ls(root: str, patterns: list[str]) -> list[str]:
    files: list[str] = []
    with working_dir(root):
        cp = subprocess.run(["repo", "list"], capture_output=True, text=True)
        paths = [line.split(":")[0].strip() for line in cp.stdout.splitlines()]
        for p in paths:
            proj_files = git_ls(p, patterns)
            if p == ".":
                files.extend(proj_files)
            else:
                files.extend([os.path.join(p, f) for f in proj_files])
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
