# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

from ....config.argparsing import Parser
from ....config.schemas import testpaths_schema
from ....third_party.color import colorize
from ....util.filesystem import working_dir
from ....util.string import strip_quotes
from ....workspace import NotAWorkspaceError
from ....workspace import Workspace


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

    def __call__(self, parser, namespace, values, option_string=None):
        """When this function call exits, the following variables will be set on ``namespace``:

        paths: dict[str, list[str]]
          paths.keys() are the roots to search for new tests in
          paths.values() are (optional) specific files to read from the associated root
        on_options: list[str]
          filter tests that don't contain this option spec
        script_args: list[str]
          arguments to pass directly to test scripts
        keyword_exprs: list[str]
          keyword filtering expressions

        """

        workspace: Workspace | None
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            workspace = None

        setdefault(namespace, "on_options", [])
        setdefault(namespace, "off_options", [])
        setdefault(namespace, "script_args", [])
        setdefault(namespace, "keyword_exprs", [])

        setdefault(namespace, "paths", {})
        setdefault(namespace, "runtag", None)
        setdefault(namespace, "start", None)
        setdefault(namespace, "casespecs", None)

        if option_string == "-f":
            namespace.paths.update(self.read_paths(values))
            return

        ns = self.parse(values)
        if ns.on_options:
            namespace.on_options.extend(ns.on_options)
        if ns.off_options:
            namespace.off_options.extend(ns.off_options)
        if ns.script_args:
            namespace.script_args.extend(ns.script_args)
        if ns.keyword_exprs:
            namespace.keyword_exprs.extend(ns.keyword_exprs)

        pathspec: list[str] = ns.pathspec or []
        for path in pathspec:
            if os.path.isfile(path) and path.endswith("testcases.lock"):
                raise NotImplementedError
            elif workspace is not None and workspace.is_tag(path):
                namespace.runtag = path
            elif workspace is not None and workspace.inside_view(path):
                namespace.start = os.path.abspath(path)
            elif os.path.isfile(path) and is_test_file(path):
                abspath = os.path.abspath(path)
                root, name = os.path.split(abspath)
                namespace.paths.setdefault(root, []).append(name)
                namespace.keyword_exprs.append(abspath)
            elif os.path.isdir(path):
                namespace.paths.setdefault(path, [])
            elif path.startswith(("git@", "repo@")):
                if not os.path.isdir(path.partition("@")[2]):
                    p = path.partition("@")[2]
                    raise ValueError(f"{p}: no such file or directory")
                namespace.paths.setdefault(path, [])
            elif os.pathsep in path and os.path.exists(path.replace(os.pathsep, os.path.sep)):
                # allow specifying as root:name
                root, name = path.split(os.pathsep, 1)
                namespace.paths.setdefault(root, []).append(name.replace(os.pathsep, os.path.sep))
            elif path.startswith("/") and not os.path.exists(path):
                setdefault(namespace, "casespecs", []).append(path)
            else:
                raise ValueError(f"{path}: no such file or directory")

        check_mutually_exclusive_pathspec_args(namespace)

        return

    @staticmethod
    def setup_parser(parser: Parser) -> None:
        parser.add_argument(
            "-f",
            metavar="file",
            action=PathSpec,
            dest="f_pathspec",
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )
        parser.add_argument(
            "pathspec",
            metavar="pathspec [--] [user args...]",
            action=PathSpec,
            nargs=argparse.REMAINDER,
            help="Test file[s] or directories to search. "
            "See 'canary help --pathspec' for help on the path specification",
        )

    @staticmethod
    def parse(values: list[str]) -> argparse.Namespace:
        """Split ``values`` into:
        - on_options: anything prefixed with +
        - off_options: anything prefixed with ~
        - keyword expressions: anything prefixed with %
        - pathspec: everything else, up to ``--``
        - script_args: anything following ``--``
        """
        namespace = argparse.Namespace(
            on_options=[],
            off_options=[],
            script_args=[],
            keyword_exprs=[],
            pathspec=[],
        )
        for i, item in enumerate(values):
            if item == "--":
                namespace.script_args = values[i + 1 :]
                break
            if item.startswith("+"):
                namespace.on_options.append(item[1:])
            elif item.startswith("~"):
                namespace.off_options.append(item[1:])
            elif item.startswith("%"):
                namespace.keyword_exprs.append(strip_quotes(item[1:]))
            else:
                namespace.pathspec.append(item)
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


def is_test_file(arg: str) -> bool:
    from .... import config
    from ...types import ScanPath
    p = ScanPath(root=arg, paths=[])
    hook = config.pluginmanager.hook.canary_collect_generators
    return hook(scan_path=p) is not None


def check_mutually_exclusive_pathspec_args(ns: argparse.Namespace) -> None:
    if ns.casespecs:
        if any([ns.paths, ns.runtag, ns.start]):
            raise TypeError("/HASH pathspec argument[s] incompatible with other pathspec arguments")
    if ns.start:
        if any([ns.paths, ns.runtag, ns.casespecs]):
            raise TypeError(f"{ns.start}: argument incompatible with other pathspec arguments")
    if ns.runtag:
        if any([ns.paths, ns.start, ns.casespecs]):
            raise TypeError(f"{ns.runtag}: argument incompatible with other pathspec arguments")
    if ns.paths:
        if any([ns.runtag, ns.start, ns.casespecs]):
            raise TypeError("PATH argument[s] incompatible with other pathspec arguments")
