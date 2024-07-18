import argparse
import json
import os

from ...config.schemas import testpaths_schema
from ...finder import is_test_file
from ...session import Session
from ...test.case import TestCase
from ...third_party.color import colorize
from ...util.filesystem import working_dir


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
        on_options: list[str] = []
        pathspec: list[str] = []
        for item in args.pathspec:
            if item.startswith("+"):
                on_options.append(item[1:])
            else:
                pathspec.append(item)
        args.pathspec = pathspec
        args.on_options.extend(on_options)
        if Session.find_root(os.getcwd()) is not None:
            return PathSpec.parse_in_session(args)
        else:
            return PathSpec.parse_new_session(args)

    @staticmethod
    def parse_new_session(args: argparse.Namespace) -> None:
        args.mode = "w"
        args.paths = {}
        if not args.pathspec:
            args.paths.setdefault(os.getcwd(), [])
            return
        for path in args.pathspec:
            if os.path.exists(path) and path.endswith((".yaml", ".yml", ".json")):
                PathSpec.read_paths(path, args.paths)
            elif os.path.isfile(path) and is_test_file(path):
                root, name = os.path.split(os.path.abspath(path))
                args.paths.setdefault(root, []).append(name)
            elif os.path.isdir(path):
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
        if args.work_tree is not None:
            raise ValueError(f"work_tree={args.work_tree} incompatible with path arguments")
        args.work_tree = Session.find_root(os.getcwd())

        pathspec: list[str] = []
        for i, p in enumerate(args.pathspec):
            if TestCase.spec_like(p):
                setdefault(args, "case_specs", []).append(p)
                args.pathspec[i] = None
            elif p.startswith("^"):
                args.mode = "b"
                try:
                    lot_no, batch_no = [int(_) for _ in p[1:].split(":")]
                except ValueError:
                    raise ValueError(f"{p}: invalid batch spec") from None
                setdefault(args, "batch_no", batch_no)
                setdefault(args, "lot_no", lot_no)
                if "NVTEST_LOT_NO" not in os.environ:
                    os.environ["NVTEST_LOT_NO"] = str(lot_no)
                elif not lot_no == int(os.environ["NVTEST_LOT_NO"]):
                    raise ValueError("env batch lot inconsistent with cli batch lot")
                if "NVTEST_BATCH_NO" not in os.environ:
                    os.environ["NVTEST_BATCH_NO"] = str(batch_no)
                elif not batch_no == int(os.environ["NVTEST_BATCH_NO"]):
                    raise ValueError("env batch number inconsistent with cli batch number")
            else:
                pathspec.append(p)
        if getattr(args, "case_specs", None):
            if pathspec:
                raise ValueError("do not mix /ID with other pathspec arguments")
        elif getattr(args, "batch_no", None):
            if pathspec:
                raise ValueError("do not mix ^BATCH with other pathspec arguments")
        if len(pathspec) > 1:
            raise ValueError("incompatible input path arguments")
        if args.wipe:
            raise ValueError("wipe=True incompatible with path arguments")
        if pathspec:
            path = os.path.abspath(pathspec.pop(0))
            if not os.path.exists(path):
                raise ValueError(f"{path}: no such file or directory")
            if path.endswith((".yaml", ".yml", ".json")):
                raise ValueError(f"path={path} is an illegal pathspec argument in re-use mode")
            if not path.startswith(args.work_tree):
                raise ValueError("path arg must be a child of the work tree")
            args.start = os.path.relpath(path, args.work_tree)
            if os.path.isfile(path):
                if is_test_file(path):
                    name = os.path.splitext(os.path.basename(path))[0]
                    if args.keyword_expr:
                        args.keyword_expr += f" and {name}"
                    else:
                        args.keyword_expr = name
                else:
                    raise ValueError(f"{path}: unrecognized file extension")
            elif not args.keyword_expr:
                kwds: list[str] = []
                for f in os.listdir(path):
                    if is_test_file(f):
                        name = os.path.splitext(os.path.basename(f))[0]
                        kwds.append(name)
                args.keyword_expr = " and ".join(kwds)
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
    def description() -> str:
        pathspec_help = """\
The behavior %(run)s is context dependent.

For %(new)s test sessions, the %(pathspec)s argument is scanned for test files to add
to the session.  %(pathspec)s can be one (or more) of the following types:

• directory name: the directory is recursively searched for test files ending in
  '.vvt', '.pyt', or CTestTestfile.cmake;
• '.vvt', '.pyt', or CTestTestfile.cmake file: specific test files; and
• '.json' or '.yaml' file: file containing specific paths to tests and/or directories with the following schema:

  .. code-block:: yaml

    testpaths:
    - root: str
      paths: [path, ...]

  where %(paths)s is a list of file paths relative to %(root)s.

For %(existing)s test sessions, the %(pathspec)s argument is scanned for tests to rerun.
%(pathspec)s can be one (or more) of the following types:

• directory name: run test files in this directory and its children;
• test id: run this specific test, specified as ``%(id)s``;
• test file: run the test defined in this file; and
• batch spec: run this batch of tests, specified as ``%(batch_no)s``.
""" % {
            "run": bold("nvtest run"),
            "new": bold("new"),
            "existing": bold("existing"),
            "pathspec": bold("pathspec"),
            "id": bold("/ID"),
            "batch_no": bold("^BATCH_LOT:BATCH_NO"),
            "paths": bold("paths"),
            "root": bold("root"),
        }
        return pathspec_help


def bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)
