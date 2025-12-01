# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import dataclasses
import fnmatch
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterator

from . import config
from .config.argparsing import Parser
from .config.schemas import testpaths_schema
from .generator import AbstractTestGenerator
from .hookspec import hookimpl
from .third_party.color import colorize
from .util import logging
from .util.filesystem import filesystem_root
from .util.filesystem import working_dir

if TYPE_CHECKING:
    from .generator import AbstractTestGenerator

logger = logging.get_logger(__name__)


def canary_collect(collector: "Collector") -> list["AbstractTestGenerator"]:
    config.pluginmanager.hook.canary_collectstart(collector=collector)
    config.pluginmanager.hook.canary_collectitems(collector=collector)
    config.pluginmanager.hook.canary_collect_modifyitems(collector=collector)
    config.pluginmanager.hook.canary_collect_report(collector=collector)
    return collector.emit_generators()


@hookimpl
def canary_collectstart(collector: "Collector") -> None:
    dirs = ["__pycache__", ".git", ".svn", ".hg", config.get("view") or "TestResults"]
    collector.add_skip_dirs(dirs)


@hookimpl(specname="canary_collectitems")
def collect_from_paths(collector: "Collector") -> None:
    for scanpath in collector.iter_scanpaths():
        root_path = Path(scanpath.root)
        if not root_path.exists():
            continue
        fs_root = filesystem_root(scanpath.root)
        pm = logger.progress_monitor(f"@*{{Collecting}} test case generators in {fs_root}")
        full_path = root_path if scanpath.path is None else root_path / scanpath.path
        if full_path.is_file() and collector.matches(full_path.name):
            assert scanpath.path is not None
            relpath = os.path.relpath(str(full_path), scanpath.root)
            collector.add_file(str(scanpath.root), relpath)
        elif full_path.is_dir():
            paths: list[str] = []
            for dirname, dirs, files in os.walk(full_path):
                if collector.skip(dirname):
                    dirs[:] = ()
                    continue
                for f in files:
                    if collector.matches(f):
                        relpath = os.path.relpath(os.path.join(dirname, f), scanpath.root)
                        paths.append(str(relpath))
            if paths:
                collector.add_files(scanpath.root, paths)
        pm.done()


@hookimpl(specname="canary_collectitems")
def collect_from_vc(collector: "Collector") -> None:
    for root in collector.scanpaths:
        if not root.startswith(("git@", "repo@")):
            continue
        type, _, vcroot = root.partition("@")
        files = _from_version_control(type, vcroot, collector.file_patterns)
        collector.add_files(vcroot, files)


def _from_version_control(type: str, root: str, file_patterns: list[str]) -> list[str]:
    """Find files in version control repository (only git supported)"""
    if type not in ("git", "repo"):
        raise TypeError("Unknown vc type {type!r}, choose from git, repo")
    if type == "git":
        return git_ls(root, file_patterns)
    else:
        return repo_ls(root, file_patterns)


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


@dataclasses.dataclass
class ScanPath:
    root: str
    path: str | None = None


@dataclasses.dataclass
class Collector:
    file_patterns: list[str] = dataclasses.field(default_factory=list, init=False)
    skip_dirs: list[str] = dataclasses.field(default_factory=list, init=False)
    scanpaths: dict[str, list[str]] = dataclasses.field(default_factory=dict, init=False)
    files: dict[str, list[str]] = dataclasses.field(default_factory=dict, init=False)

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        parser.add_argument(
            "-f",
            action=PathSpec,
            dest="f_pathspec",
            metavar="file",
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )
        parser.add_argument(
            "scanpaths",
            action=PathSpec,
            nargs=argparse.REMAINDER,
            metavar="pathspec [--] [user args...]",
            help="Test file[s] or directories to search. "
            "See 'canary help --pathspec' for help on the path specification",
        )

    def add_file_patterns(self, *patterns: str) -> None:
        for pattern in patterns:
            if pattern not in self.file_patterns:
                self.file_patterns.append(pattern)

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

    def iter_scanpaths(self) -> Iterator[ScanPath]:
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
        for root, paths in self.scanpaths.items():
            for path in paths:
                yield root, path

    def matches(self, f: str) -> bool:
        for pattern in self.file_patterns:
            if fnmatch.fnmatchcase(f, pattern):
                return True
        return False

    def emit_generators(self) -> list["AbstractTestGenerator"]:
        errors = 0
        generators: list["AbstractTestGenerator"] = []
        for root, paths in self.files.items():
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


def generate_one(args) -> tuple[bool, "AbstractTestGenerator | None"]:
    pm = config.pluginmanager.hook
    root, f = args
    try:
        gen = pm.canary_testcase_generator(root=root, path=f)
        return True, gen
    except Exception:
        logger.exception(f"Failed to parse test from {root}/{f}")
        return False, None


def setdefault(obj, attr, default):
    if getattr(obj, attr, None) is None:
        setattr(obj, attr, default)
    return getattr(obj, attr)


class PathSpec(argparse.Action):
    """Parse the ``pathspec`` argument.

    The ``pathspec`` can take on different meanings, each entry in pathspec
    can represent one of

    - an input file containing search path information when creating a new session
    - a directory to search for test files when creating a new session
    - a filter when re-using a previous session
    - a test ID to run

    """

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        """When this function call exits, the following variables will be set on ``namespace``:

        scanpaths: dict[str, list[str]]
          paths.keys() are the roots to search for new tests in
          paths.values() are (optional) specific files to read from the associated root

        """
        from .workspace import NotAWorkspaceError
        from .workspace import Workspace

        workspace: Workspace | None
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            workspace = None

        setdefault(namespace, "script_args", [])
        setdefault(namespace, "scanpaths", {})
        setdefault(namespace, "runtag", None)
        setdefault(namespace, "start", None)
        setdefault(namespace, "specids", None)

        if self.dest == "f_pathspec":
            namespace.scanpaths.update(self.read_paths(values))
            return

        assert isinstance(values, list)
        ns = self.parse(values)
        if ns.script_args:
            namespace.script_args.extend(ns.script_args)

        scanpaths: list[str] = ns.scanpaths or []
        for path in scanpaths:
            if os.path.isfile(path) and path.endswith("testcases.lock"):
                raise NotImplementedError
            elif workspace is not None and workspace.is_tag(path):
                namespace.runtag = path
            elif workspace is not None and workspace.inside_view(path):
                namespace.start = os.path.abspath(path)
            elif os.path.isfile(path):
                abspath = os.path.abspath(path)
                root, name = os.path.split(abspath)
                namespace.scanpaths.setdefault(root, []).append(name)
            elif os.path.isdir(path):
                namespace.scanpaths.setdefault(os.path.abspath(path), [])
            elif path.startswith(("git@", "repo@")):
                if not os.path.isdir(path.partition("@")[2]):
                    p = path.partition("@")[2]
                    raise ValueError(f"{p}: no such file or directory")
                namespace.scanpaths.setdefault(path, [])
            elif os.pathsep in path and os.path.exists(path.replace(os.pathsep, os.path.sep)):
                # allow specifying as root:name
                root, name = path.split(os.pathsep, 1)
                namespace.scanpaths.setdefault(os.path.abspath(root), []).append(
                    name.replace(os.pathsep, os.path.sep)
                )
            elif path.startswith("/") and not os.path.exists(path):
                setdefault(namespace, "specids", []).append(path[1:])
            else:
                raise ValueError(f"{path}: no such file or directory")

        check_mutually_exclusive_pathspec_args(namespace)

        return

    @staticmethod
    def parse(values: list[str]) -> argparse.Namespace:
        """Split ``values`` into:
        - pathspec: everything up to ``--``
        - script_args: anything following ``--``
        """
        namespace = argparse.Namespace(script_args=[], scanpaths=[])
        for i, item in enumerate(values):
            if item == "--":
                namespace.script_args = values[i + 1 :]
                break
            else:
                namespace.scanpaths.append(item)
        return namespace

    @staticmethod
    def read_paths(file: str) -> dict[str, list[str]]:
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

    @staticmethod
    def pathspec_help() -> str:
        pathspec_help = """\
pathspec syntax:

  pathspec [-- ...]

  new test sessions:
    %(path)s                                   scan path recursively for test generators
    %(file)s                                   use this test generator
    %(lock)s                         run tests in this lock file
                                           (produced by %(find)s)
    %(git)s@path                               find tests under git version control at path
    %(repo)s@path                              find tests under repo version control at path

  inside existing test sessions:
    %(relpath)s                                   rerun test cases in this directory and its children
    %(relfile)s                                   rerun the test case defined in this file
    %(hash)s                                  rerun this test case

  examples:
    canary run path                        scan path for tests to run
    canary -C TestResults run .            rerun tests in . (and its children)
    canary -C TestResults run /7yral9i     rerun test case with hash 7yral9i

  script arguments:
    Any argument following the %(sep)s separator is passed directly to each test script's command line.
""" % {
            "file": bold("file"),
            "path": bold("path"),
            "git": bold("git"),
            "repo": bold("repo"),
            "lock": bold("testcases.lock"),
            "find": bold("canary find --lock ..."),
            "relpath": bold("path"),
            "relfile": bold("file"),
            "hash": bold("/hash"),
            "sep": bold("--"),
        }
        return pathspec_help

    @staticmethod
    def pathfile_help() -> str:
        text = """\
pathspec file schema syntax:

  {
    "testpaths": [
      {
        "root": str,
        "paths": [str]
      }
    ]
  }"""
        return text


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)


def code(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"``{arg}``"
    return colorize("@*{%s}" % arg)


def check_mutually_exclusive_pathspec_args(ns: argparse.Namespace) -> None:
    if ns.specids:
        if any([ns.scanpaths, ns.runtag, ns.start]):
            raise TypeError("/HASH pathspec argument[s] incompatible with other pathspec arguments")
    if ns.start:
        if any([ns.scanpaths, ns.runtag, ns.specids]):
            raise TypeError(f"{ns.start}: argument incompatible with other pathspec arguments")
    if ns.runtag:
        if any([ns.scanpaths, ns.start, ns.specids]):
            raise TypeError(f"{ns.runtag}: argument incompatible with other pathspec arguments")
    if ns.scanpaths:
        if any([ns.runtag, ns.start, ns.specids]):
            raise TypeError("PATH argument[s] incompatible with other pathspec arguments")
