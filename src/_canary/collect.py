# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import dataclasses
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable
from typing import Iterator
from typing import Type

from . import config
from .config.argparsing import Parser
from .config.schemas import testpaths_schema
from .generator import AbstractTestGenerator
from .hookspec import hookimpl
from .util import logging
from .util.filesystem import working_dir

logger = logging.get_logger(__name__)

vc_prefixes = ("git@", "repo@")


def recursedirs_type(arg: str) -> dict[str, list[str]]:
    if os.path.isdir(arg):
        return {os.path.abspath(arg): []}
    elif os.path.isfile(arg):
        d, f = os.path.split(os.path.abspath(arg))
        return {d: [f]}
    elif ":" in arg:
        root, _, path = arg.partition(":")
        if os.path.isdir(root) and os.path.exists(os.path.join(root, path)):
            return {root: [path]}
    raise ValueError(f"{arg}: no such file or directory")


def read_recursedirs(file: str) -> dict[str, list[str]]:
    data: dict
    if file.endswith(".json"):
        with open(file, "r") as fh:
            data = json.load(fh)
    else:
        import yaml

        with open(file, "r") as fh:
            data = yaml.safe_load(fh)
    testpaths_schema.validate(data)
    file_dir = os.path.abspath(os.path.dirname(file) or ".")
    paths: dict[str, list[str]] = {}
    with working_dir(file_dir):
        for p in data["testpaths"]:
            if isinstance(p, str):
                paths.setdefault(os.path.abspath(p), [])
            else:
                paths.setdefault(os.path.abspath(p["root"]), []).extend(p["paths"])
    return paths


class update_action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None) -> None:
        assert isinstance(values, dict)
        value = getattr(namespace, self.dest, None) or {}
        value.update(values)
        setattr(namespace, self.dest, value)


class Collector:
    def __init__(self) -> None:
        self.skip_dirs: list[str] = []
        self.scanpaths: dict[str, list[str]] = {}
        self.files: dict[str, list[str]] = {}  # root: paths
        self.generators: list["AbstractTestGenerator"] = []
        self.types: set[Type[AbstractTestGenerator]] = set()

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        parser.add_argument(
            "-f",
            dest="scanpaths",
            metavar="file",
            action=update_action,
            type=read_recursedirs,
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )
        parser.add_argument(
            "-r",
            dest="scanpaths",
            metavar="PATH",
            action=update_action,
            type=recursedirs_type,
            help="Recursively search PATH for test generators",
        )

    def run(self) -> list["AbstractTestGenerator"]:
        config.pluginmanager.hook.canary_collectstart(collector=self)
        for scanpath in self.iter_scanpaths():
            if scanpath.root.startswith(vc_prefixes):
                self.collect_from_vc(scanpath.root)
            elif os.path.exists(scanpath.root):
                self.collect_from_path(scanpath)
            else:
                logger.warning(f"Skipping non-existent path {scanpath.root}")
        config.pluginmanager.hook.canary_collect_modifyitems(collector=self)
        self.finalize()
        config.pluginmanager.hook.canary_collect_report(collector=self)
        return self.generators

    def finalize(self) -> None:
        pm = logger.progress_monitor("[bold]Instantiating[/] generators from collected files")
        errors = 0
        generators: list["AbstractTestGenerator"] = []
        all_paths: list[tuple[set[Type[AbstractTestGenerator]], str, str]] = []
        for root, paths in self.files.items():
            all_paths.extend([(self.types, root, path) for path in paths])
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
        pm.done()
        self.generators.clear()
        self.generators.extend(generators)
        return

    def collect_from_path(self, scanpath: "ScanPath") -> None:
        root_path = Path(scanpath.root)
        assert root_path.exists()
        cwd = Path.cwd()
        sp = root_path if not root_path.is_relative_to(cwd) else root_path.relative_to(cwd)
        pm = logger.progress_monitor(f"[bold]Collecting[/] generator files from {sp}")
        full_path = root_path if scanpath.path is None else root_path / scanpath.path
        if full_path.is_file() and self.matches(full_path.name):
            assert scanpath.path is not None
            relpath = os.path.relpath(str(full_path), scanpath.root)
            self.add_file(str(scanpath.root), str(relpath))
        elif full_path.is_dir():
            paths: list[str] = []
            for dirname, dirs, files in os.walk(full_path):
                if self.skip(dirname):
                    dirs[:] = ()
                    continue
                for f in files:
                    if self.matches(f):
                        relpath = os.path.relpath(os.path.join(dirname, f), scanpath.root)
                        paths.append(str(relpath))
            if paths:
                self.add_files(scanpath.root, paths)
        pm.done()

    def collect_from_vc(self, root: str) -> None:
        assert root.startswith(vc_prefixes)
        type, _, vcroot = root.partition("@")
        pm = logger.progress_monitor(
            f"[bold]Collecting[/] generator files from {vcroot} using {type}"
        )
        files = _from_version_control(type, vcroot, self.file_patterns)
        self.add_files(vcroot, files)
        pm.done()

    def add_generator(self, generator: Type[AbstractTestGenerator]) -> None:
        self.types.add(generator)

    @property
    def file_patterns(self) -> set[str]:
        return {pat for type in self.types for pat in type.file_patterns}

    def add_skip_dirs(self, dirs: list[str]) -> None:
        for dir in dirs:
            if dir not in self.skip_dirs:
                self.skip_dirs.append(dir)

    def skip(self, dirname: str) -> bool:
        return os.path.basename(dirname) in self.skip_dirs

    def add_scanpaths(self, scanpaths: dict[str, list[str]]) -> None:
        for root, paths in scanpaths.items():
            self.add_scanpath(root, paths)

    def add_scanpath(self, root: str, paths: list[str]) -> None:
        if not root.startswith(vc_prefixes):
            root = os.path.abspath(root)
        if os.path.isfile(root):
            if paths:
                raise ValueError(f"Scan paths for file {root} cannot have subpaths")
            root, tail = os.path.split(root)
            paths = [tail]
        my_paths = set(self.scanpaths.get(root, []))
        for path in paths:
            relpath = os.path.relpath(path, root) if os.path.isabs(path) else path
            if relpath.startswith(".."):
                raise ValueError(f"Subpath {relpath} must be child of {root}.")
            my_paths.add(os.path.normpath(relpath))
        self.scanpaths[root] = sorted(my_paths, key=lambda p: (len(p.split(os.sep)), p))

    def iter_scanpaths(self) -> Iterator["ScanPath"]:
        for root, paths in self.scanpaths.items():
            if not paths:
                yield ScanPath(root=root)
            else:
                for path in paths:
                    yield ScanPath(root=root, path=path)

    def add_file(self, root: str, path: str) -> None:
        self.add_files(root, [path])

    def add_files(self, root: str, paths: list[str]) -> None:
        root = os.path.abspath(root)
        my_files: set[str] = set(self.files.get(root, []))
        for path in paths:
            relpath = os.path.relpath(path, root) if os.path.isabs(path) else path
            if relpath.startswith(".."):
                raise ValueError(f"Subpath {relpath} must be child of {root}.")
            if not os.path.exists(os.path.join(root, relpath)):
                logger.warning(f"{root}/{relpath}: path does not exist")
            else:
                my_files.add(os.path.normpath(relpath))
        self.files[root] = sorted(my_files, key=lambda p: (len(p.split(os.sep)), p))

    def remove_file(self, root: str, path: str) -> None:
        paths = self.files.pop(root, [])
        relpath = os.path.relpath(path, root) if os.path.isabs(path) else path
        if relpath in paths:
            paths.remove(relpath)
        if paths:
            self.files[root] = paths

    def iter_files(self) -> Iterator[tuple[str, str]]:
        for root, paths in self.files.items():
            for path in paths:
                yield root, path

    def matches(self, f: str) -> bool:
        for type in self.types:
            if type.matches(f):
                return True
        return False


@hookimpl
def canary_collectstart(collector: "Collector") -> None:
    dirs = ["__pycache__", ".git", ".svn", ".hg", config.get("view") or "TestResults"]
    collector.add_skip_dirs(dirs)


def _from_version_control(type: str, root: str, file_patterns: Iterable[str]) -> list[str]:
    """Find files in version control repository"""
    if type == "git":
        return git_ls(root, file_patterns)
    elif type == "repo":
        return repo_ls(root, file_patterns)
    else:
        raise TypeError(f"Unknown vc type {type!r}, choose from git, repo")


def git_ls(root: str, patterns: Iterable[str]) -> list[str]:
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


def repo_ls(root: str, patterns: Iterable[str]) -> list[str]:
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


@dataclasses.dataclass
class ScanPath:
    root: str
    path: str | None = None


def generate_one(args) -> tuple[bool, "AbstractTestGenerator | None"]:
    types, root, f = args
    try:
        for type in types:
            if gen := type.factory(root=root, path=f):
                return True, gen
        logger.error(f"{f}: no matching generator found")
        return False, None
    except Exception:
        logger.exception(f"Failed to parse test from {root}/{f}")
        return False, None
