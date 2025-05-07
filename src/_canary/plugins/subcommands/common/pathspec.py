# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

from ....config.argparsing import Parser
from ....config.schemas import testpaths_schema
from ....finder import is_test_file
from ....test.case import TestCase
from ....third_party.color import colorize
from ....util.filesystem import find_work_tree
from ....util.filesystem import working_dir


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
    - a batch number to run

    """

    def __call__(self, parser, args, values, option_string=None):
        if self.dest == "f_pathspec":
            work_tree = find_work_tree(os.getcwd())
            if work_tree is not None:
                raise ValueError(f"-f {values} is illegal in re-use mode")
            paths = self.read_paths(values)
            args.mode = "w"
            args.start = None
            setattr(args, self.dest, values)
            setdefault(args, "paths", {}).update(paths)
            return

        on_options, off_options, pathspec, script_args = self.parse(values)
        if not pathspec and getattr(args, "f_pathspec", None):
            # use values from file only
            return
        if on_options:
            setdefault(args, "on_options", []).extend(on_options)
        if off_options:
            setdefault(args, "off_options", []).extend(off_options)
        args.script_args = script_args or None
        args.pathspec = pathspec

        work_tree = find_work_tree(os.getcwd())
        if work_tree is None:
            args.mode = "w"
            args.start = None
            paths = self.parse_new_session(pathspec)
            setdefault(args, "paths", {}).update(paths)
            return

        assert work_tree is not None
        if f := getattr(args, "f_pathspec", None):
            raise ValueError(f"-f {f} is illegal in re-use mode")
        if getattr(args, "wipe", None):
            raise ValueError("-w option is illegal in re-use mode")
        if getattr(args, "work_tree", None):
            raise ValueError(f"-d {args.work_tree} option is illegal in re-use mode")

        args.work_tree = work_tree
        case_specs, batch_id, path = self.parse_in_session(pathspec)
        args.start = None
        args.mode = "b" if batch_id else "a"
        args.case_specs = case_specs or None
        args.batch_id = batch_id
        if path is not None:
            if not path.startswith(args.work_tree):  # type: ignore
                raise ValueError("path arg must be a child of the work tree")
            args.start = os.path.relpath(path, args.work_tree)
            if os.path.isfile(path):
                if is_test_file(path):
                    name = os.path.splitext(os.path.basename(path))[0]
                    setdefault(args, "keyword_exprs", []).append(name)
                else:
                    raise ValueError(f"{path}: unrecognized file extension")
            elif getattr(args, "keyword_exprs", None) is None:
                kwds = []
                for f in os.listdir(path):
                    if is_test_file(f):
                        name = os.path.splitext(os.path.basename(f))[0]
                        kwds.append(name)
                if kwds:
                    args.keyword_exprs = kwds

    @staticmethod
    def setup_parser(parser: Parser) -> None:
        parser.add_argument(
            "-f",
            metavar="file",
            action=PathSpec,
            dest="f_pathspec",
            help="Read test paths from a json or yaml file. "
            'The file schema is {"testpaths": ["root": str, "paths": [str, ...], ...]}, where '
            "paths is a list of files relative to root",
        )
        parser.add_argument(
            "pathspec",
            metavar="pathspec [--] [user args...]",
            action=PathSpec,
            nargs=argparse.REMAINDER,
            help="Test file[s] or directories to search",
        )

    @staticmethod
    def parse(values: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
        """Split ``values`` into:
        - on_options: anything prefixed with +
        - off_options: anything prefixed with ~
        - script_args: anything following ``--``
        - pathspec: everything else
        """
        on_options: list[str] = []
        off_options: list[str] = []
        script_args: list[str] = []
        pathspec: list[str] = []
        for i, item in enumerate(values):
            if item == "--":
                script_args = values[i + 1 :]
                break
            if item.startswith("+"):
                on_options.append(item[1:])
            elif item.startswith("~"):
                off_options.append(item[1:])
            else:
                pathspec.append(item)
        return on_options, off_options, pathspec, script_args

    @staticmethod
    def parse_new_session(pathspec: list[str]) -> dict[str, list[str]]:
        paths: dict[str, list[str]] = {}
        if not pathspec:
            paths.setdefault(os.getcwd(), [])
            return paths
        for path in pathspec:
            if os.path.isfile(path) and is_test_file(path):
                root, name = os.path.split(os.path.abspath(path))
                paths.setdefault(root, []).append(name)
            elif os.path.isdir(path):
                paths.setdefault(path, [])
            elif path.startswith(("git@", "repo@")):
                if not os.path.isdir(path.partition("@")[2]):
                    p = path.partition("@")[2]
                    raise ValueError(f"{p}: no such file or directory")
                paths.setdefault(path, [])
            elif os.pathsep in path and os.path.exists(path.replace(os.pathsep, os.path.sep)):
                # allow specifying as root:name
                root, name = path.split(os.pathsep, 1)
                paths.setdefault(root, []).append(name.replace(os.pathsep, os.path.sep))
            else:
                raise ValueError(f"{path}: no such file or directory")
        return paths

    @staticmethod
    def parse_in_session(values: list[str]) -> tuple[list[str], str | None, str | None]:
        paths: list[str] = []
        case_specs: list[str] = []
        batch_id: str | None = None
        path: str | None = None
        for p in values:
            if TestCase.spec_like(p):
                case_specs.append(p)
            elif p.startswith("^"):
                batch_id = p[1:]
                if "CANARY_BATCH_ID" not in os.environ:
                    os.environ["CANARY_BATCH_ID"] = str(batch_id)
                elif not batch_id == os.environ["CANARY_BATCH_ID"]:
                    raise ValueError("env batch id inconsistent with cli batch id")
            else:
                paths.append(p)
        if len([1 for _ in (case_specs, batch_id, paths) if _]) > 1:
            raise ValueError("do not mix /hash, ^hash, and other pathspec arguments")
        if len(paths) > 1:
            raise ValueError("incompatible input path arguments")
        if paths:
            path = os.path.abspath(paths.pop(0))
            if not os.path.exists(path):
                raise ValueError(f"{path}: no such file or directory")
        return case_specs, batch_id, path

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
    def description() -> str:
        pathspec_help = """\
pathspec syntax:

  pathspec [-- ...]

  new test sessions:
    %(path)s                                   scan path recursively for test generators
    %(file)s                                   use this test generator
    %(git)s@path                               find tests under git version control at path
    %(repo)s@path                              find tests under repo version control at path

  inside existing test sessions:
    %(relpath)s                                   rerun test cases in this directory and its children
    %(relfile)s                                   rerun the test case defined in this file
    %(hash)s                                  rerun this test case
    %(batch)s                                  run this batch of tests

  examples:
    canary run path                        scan path for tests to run
    canary -C TestResults run .            rerun tests in . (and its children)
    canary -C TestResults run /7yral9i     rerun test case with hash 7yral9i
    canary -C TestResults run ^h6tvbax     run tests in batch h6tvbax

  script arguments:
    Any argument following the %(sep)s separator is passed directly to each test script's command line.
""" % {
            "file": bold("file"),
            "path": bold("path"),
            "git": bold("git"),
            "repo": bold("repo"),
            "relpath": bold("path"),
            "relfile": bold("file"),
            "hash": bold("/hash"),
            "batch": bold("^hash"),
            "sep": bold("--"),
        }
        return pathspec_help


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)


def code(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"``{arg}``"
    return colorize("@*{%s}" % arg)
