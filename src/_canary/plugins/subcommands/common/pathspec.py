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
    if not hasattr(obj, attr):
        setattr(obj, attr, default)
    return getattr(obj, attr)


class PathSpec:
    """Parse the ``pathspec`` argument.

    The ``pathspec`` can take on different meanings, each entry in pathspec
    can represent one of

    - an input file containing search path information when creating a new session
    - a directory to search for test files when creating a new session
    - a filter when re-using a previous session
    - a test ID to run
    - a batch number to run

    """

    @staticmethod
    def parse(args: argparse.Namespace) -> None:
        args.start = None
        script_args = None
        on_options: list[str] = []
        off_options: list[str] = []
        pathspec: list[str] = []
        for i, item in enumerate(args.pathspec):
            if item == "--":
                script_args = args.pathspec[i + 1 :]
                break
            if item.startswith("+"):
                on_options.append(item[1:])
            elif item.startswith("~"):
                off_options.append(item[1:])
            else:
                pathspec.append(item)
        args.pathspec = pathspec
        if on_options:
            args.on_options = getattr(args, "on_options", None) or []
            args.on_options.extend(on_options)
        if off_options:
            args.off_options = getattr(args, "off_options", None) or []
            args.off_options.extend(off_options)
        if script_args:
            args.script_args = script_args
        if find_work_tree(os.getcwd()) is not None:
            return PathSpec.parse_in_session(args)
        else:
            return PathSpec.parse_new_session(args)

    @staticmethod
    def parse_new_session(args: argparse.Namespace) -> None:
        args.mode = "w"
        args.paths = {}
        if args.f_pathspec:
            PathSpec.read_paths(args.f_pathspec, args.paths)
            if not args.pathspec:
                return
        if not args.pathspec:
            args.paths.setdefault(os.getcwd(), [])
            return
        for path in args.pathspec:
            if os.path.isfile(path) and is_test_file(path):
                root, name = os.path.split(os.path.abspath(path))
                args.paths.setdefault(root, []).append(name)
            elif os.path.isdir(path):
                args.paths.setdefault(path, [])
            elif path.startswith(("git@", "repo@")):
                if not os.path.isdir(path.partition("@")[2]):
                    p = path.partition("@")[2]
                    raise ValueError(f"{p}: no such file or directory")
                args.paths.setdefault(path, [])
            elif os.pathsep in path and os.path.exists(path.replace(os.pathsep, os.path.sep)):
                # allow specifying as root:name
                root, name = path.split(os.pathsep, 1)
                args.paths.setdefault(root, []).append(name.replace(os.pathsep, os.path.sep))
            else:
                raise ValueError(f"{path}: no such file or directory")

    @staticmethod
    def parse_in_session(args: argparse.Namespace) -> None:
        args.mode = "a"
        if getattr(args, "work_tree", None) is not None:
            raise ValueError(f"work_tree={args.work_tree} incompatible with path arguments")
        args.work_tree = find_work_tree(os.getcwd())

        pathspec: list[str] = []
        for i, p in enumerate(args.pathspec):
            if TestCase.spec_like(p):
                setdefault(args, "case_specs", []).append(p)
                args.pathspec[i] = None
            elif p.startswith("^"):
                args.mode = "b"
                batch_id = p[1:]
                setdefault(args, "batch_id", batch_id)
                if "CANARY_BATCH_ID" not in os.environ:
                    os.environ["CANARY_BATCH_ID"] = str(batch_id)
                elif not batch_id == os.environ["CANARY_BATCH_ID"]:
                    raise ValueError("env batch id inconsistent with cli batch id")
            else:
                pathspec.append(p)
        if getattr(args, "case_specs", None):
            if pathspec:
                raise ValueError("do not mix /ID with other pathspec arguments")
        elif getattr(args, "batch_id", None):
            if pathspec:
                raise ValueError("do not mix ^BATCH with other pathspec arguments")
        if len(pathspec) > 1:
            raise ValueError("incompatible input path arguments")
        if args.f_pathspec:
            raise ValueError("-f option is illegal in re-use mode")
        if getattr(args, "wipe", None) is True:
            raise ValueError("wipe=True incompatible with path arguments")
        if pathspec:
            path = os.path.abspath(pathspec.pop(0))
            if not os.path.exists(path):
                raise ValueError(f"{path}: no such file or directory")
            if not path.startswith(args.work_tree):  # type: ignore
                raise ValueError("path arg must be a child of the work tree")
            args.start = os.path.relpath(path, args.work_tree)
            if os.path.isfile(path):
                if is_test_file(path):
                    name = os.path.splitext(os.path.basename(path))[0]
                    if args.keyword_exprs:
                        args.keyword_exprs.append(name)
                    else:
                        args.keyword_exprs = [name]
                else:
                    raise ValueError(f"{path}: unrecognized file extension")
            elif not args.keyword_exprs:
                kwds: list[str] = []
                for f in os.listdir(path):
                    if is_test_file(f):
                        name = os.path.splitext(os.path.basename(f))[0]
                        kwds.append(name)
                if kwds:
                    args.keyword_exprs = kwds
        return

    @staticmethod
    def read_paths(file: str, paths: dict[str, list[str]]) -> None:
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
        with working_dir(file_dir):
            for p in data["testpaths"]:
                if isinstance(p, str):
                    paths.setdefault(os.path.abspath(p), [])
                else:
                    paths.setdefault(os.path.abspath(p["root"]), []).extend(p["paths"])

    @staticmethod
    def setup_parser(parser: Parser) -> None:
        parser.add_argument(
            "-f",
            metavar="file",
            dest="f_pathspec",
            help="Read test paths from a json or yaml file. "
            'The file schema is {"testpaths": ["root": str, "paths": [str, ...], ...]}, where '
            "paths is a list of files relative to root",
        )
        parser.add_argument(
            "pathspec",
            metavar="pathspec [--] [user args]...",
            nargs=argparse.REMAINDER,
            help="Test file[s] or directories to search",
        )

    @staticmethod
    def description() -> str:
        pathspec_help = """\
The behavior %(run)s is context dependent.

For %(new)s test sessions, the %(pathspec)s argument is scanned for test files to add
to the session.  %(pathspec)s can be one (or more) of the following types:

• directory name: the directory is recursively searched for recognized test file extensions;
• VCS@directory name: find tests under version control; and
• specific test files.

VCS should be one of 'git' or 'repo'.  This method can potentially much faster than the default recursive search.

For %(existing)s test sessions, the %(pathspec)s argument is scanned for tests to rerun.
%(pathspec)s can be one (or more) of the following types:

• directory name: run test files in this directory and its children;
• test id: run this specific test, specified as %(id)s;
• test file: run the test defined in this file; and
• batch spec: run this batch of tests, specified as %(batch_id)s.

Any argument following the %(sep)s separator is passed directly to each test script's command line.
""" % {
            "run": code("canary run"),
            "new": bold("new"),
            "existing": bold("existing"),
            "pathspec": code("pathspec"),
            "id": code("/ID"),
            "batch_id": code("^BATCH_ID"),
            "sep": code("--"),
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
