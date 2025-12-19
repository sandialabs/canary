# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from ... import config
from ...collect import vc_prefixes
from ...config.schemas import testpaths_schema
from ...generate import Generator
from ...hookspec import hookimpl
from ...select import Selector
from ...util import json_helper as json
from ...util import logging
from ...util.filesystem import working_dir
from ...util.rich import bold
from ...util.string import pluralize
from ...workspace import NotAWorkspaceError
from ...workspace import Workspace
from ..types import CanarySubcommand
from .common import add_resource_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testspec import ResolvedSpec

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Run())


class Run(CanarySubcommand):
    name = "run"
    description = "Find and run tests from a pathspec"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        parser.set_defaults(banner=True)
        parser.add_argument(
            "-w",
            dest="wipe_workspace",
            nargs=0,
            action=WipeAction,
            help="Remove test execution directory, if it exists [default: %(default)s]",
        )
        parser.add_argument(
            "-d",
            "--work-tree",
            action=DeprecatedStoreAction,
            dest="work_tree",
            help=argparse.SUPPRESS,
        )
        parser.add_argument(
            "-f",
            action=PathSpec,
            dest="f_pathspec",
            metavar="file",
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )
        Generator.setup_parser(parser)
        Selector.setup_parser(parser, tagged="optional")
        parser.add_argument(
            "--only",
            choices=("not_pass", "failed", "not_run", "all", "changed"),
            default="not_pass",
            help="Which tests to run after selection\n\n"
            "  all      - run all selected tests, even if already passing\n\n"
            "  failed   - run only previously failing tests\n\n"
            "  not_run  - run tests that have never been executed\n\n"
            "  changed  - run tests that whose specs have newer modification time\n\n"
            "  not_pass - run tests that are incomplete, boken, or never run (default)",
        )
        parser.add_argument(
            "--fail-fast",
            default=None,
            action="store_true",
            help="Stop after first failed test [default: %(default)s]",
        )
        parser.add_argument(
            "-P",
            "--parsing-policy",
            dest="parsing_policy",
            choices=("permissive", "pedantic"),
            help="If pedantic (default), stop if file parsing errors occur, else ignore parsing errors",
        )
        parser.add_argument(
            "--copy-all-resources",
            default=None,
            action="store_true",
            help="Do not link resources to the test directory, only copy [default: %(default)s]",
        )

        group = parser.add_argument_group("console reporting")
        group.add_argument(
            "-e",
            choices=("separate", "merge"),
            default="separate",
            dest="testcase_output_strategy",
            help="Merge a testcase's stdout and stderr or log separately [default: %(default)s]",
        )
        group.add_argument(
            "--capture",
            choices=("log", "tee"),
            default="log",
            help="Log test output to a file only (log) or log and print output "
            "to the screen (tee).  Warning: this could result in a large amount of text printed "
            "to the screen [default: log]",
        )
        group.add_argument(
            "--format",
            dest="live_name_fmt",
            choices=("long", "short"),
            default="short",
            help="Print test case fullname (long) in live status bar [default: short]",
        )
        add_resource_arguments(parser)
        parser.add_argument(
            "scanpaths",
            action=PathSpec,
            nargs=argparse.REMAINDER,
            metavar="pathspec [--] [user args...]",
            help="Test file[s] or directories to search. "
            "See 'canary help --pathspec' for help on the path specification",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        work_tree = args.work_tree or os.getcwd()
        if args.wipe_workspace:
            Workspace.remove(work_tree)
        workspace: Workspace
        reuse: bool = False
        try:
            workspace = Workspace.load(start=work_tree)
        except NotAWorkspaceError:
            workspace = Workspace.create(path=work_tree)
        # start, specids, runtag, and scanpaths are mutually exclusive
        specs: list["ResolvedSpec"]
        if args.scanpaths is not None:
            specs = workspace.create_selection(
                tag=args.tag,
                scanpaths=args.scanpaths,
                on_options=args.on_options,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        else:
            if args.start:
                logger.info(f"[bold]Running[/] tests from {args.start}")
                specs = workspace.select_from_view(path=Path(args.start))
                reuse = True
            elif args.specids:
                sids = [id[:7] for id in args.specids]
                if len(sids) > 3:
                    sids = [*sids[:2], "…", sids[-1]]
                logger.info(f"[bold]Running[/] {pluralize('spec', len(sids))} {', '.join(sids)}")
                loadspecs, runspecs = workspace.compute_rerun_list_for_specs(ids=args.specids)
                specs = loadspecs + runspecs
                setattr(args, "only", f"ids:{','.join(s.id for s in runspecs)}")
            elif args.runtag:
                logger.info(f"[bold]Running[/] tests in tag {args.runtag}")
                specs = workspace.get_selection(args.runtag)
            else:
                tag = config.get("selection:default_tag")
                logger.info(f"[bold]Running[/] tests in default tag {tag}")
                specs = workspace.get_selection(tag)
            workspace.apply_selection_rules(
                specs,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        session = workspace.run(specs, reuse_session=reuse, only=args.only)
        return session.returncode


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
        workspace: Workspace | None
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            workspace = None

        setdefault(namespace, "script_args", [])
        setdefault(namespace, "scanpaths", None)
        setdefault(namespace, "runtag", None)
        setdefault(namespace, "specids", None)
        setdefault(namespace, "start", None)

        if self.dest == "f_pathspec":
            scanpaths = getattr(namespace, "scanpaths", None) or {}
            scanpaths.update(self.read_paths(values))
            setattr(namespace, "scanpaths", scanpaths)
            return

        assert isinstance(values, list)
        ns = self.parse(values)
        if ns.script_args:
            namespace.script_args.extend(ns.script_args)

        possible_specs: list[str] = []
        items: list[str] = ns.items
        scanpaths = getattr(namespace, "scanpaths", None) or {}
        for item in items:
            if os.path.isfile(item) and item.endswith("testcases.lock"):
                raise NotImplementedError
            elif workspace is not None and workspace.is_tag(item):
                namespace.runtag = item
            elif workspace is not None and workspace.inside_view(item):
                namespace.start = os.path.abspath(item)
            elif os.path.isfile(item):
                root, name = os.path.split(os.path.abspath(item))
                scanpaths.setdefault(root, []).append(name)
            elif os.path.isdir(item):
                scanpaths.setdefault(os.path.abspath(item), [])
            elif item.startswith(vc_prefixes):
                if not os.path.isdir(item.partition("@")[2]):
                    p = item.partition("@")[2]
                    raise ValueError(f"{p}: no such file or directory")
                scanpaths.setdefault(item, [])
            elif os.pathsep in item and os.path.exists(item.replace(os.pathsep, os.path.sep)):
                # allow specifying as root:name
                root, name = item.split(os.pathsep, 1)
                scanpaths.setdefault(os.path.abspath(root), []).append(
                    name.replace(os.pathsep, os.path.sep)
                )
            else:
                possible_specs.append(item)
        if workspace and possible_specs:
            ids: list[str] = []
            found = workspace.find_specids(possible_specs)
            for i, id in enumerate(found):
                if id is None:
                    raise ValueError(
                        f"{possible_specs[i]}: not a file, directory, or test identifier"
                    )
                ids.append(id)
            setattr(namespace, "specids", ids)

        if scanpaths:
            setattr(namespace, "scanpaths", scanpaths)

        check_mutually_exclusive_pathspec_args(namespace)

        return

    @staticmethod
    def parse(values: list[str]) -> argparse.Namespace:
        """Split ``values`` into:
        - pathspec: everything up to ``--``
        - script_args: anything following ``--``
        """
        namespace = argparse.Namespace(script_args=[], items=[])
        for i, item in enumerate(values):
            if item == "--":
                namespace.script_args = values[i + 1 :]
                break
            else:
                namespace.items.append(item)
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
    %(git)s@path                               find tests under git version control at path
    %(repo)s@path                              find tests under repo version control at path

  examples:
    canary run path                        scan path for tests to run
    canary run 7yral9i                     rerun test case with hash 7yral9i

  script arguments:
    Any argument following the %(sep)s separator is passed directly to each test script's command line.
""" % {
            "file": bold("file"),
            "path": bold("path"),
            "git": bold("git"),
            "repo": bold("repo"),
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


def check_mutually_exclusive_pathspec_args(ns: argparse.Namespace) -> None:
    if ns.specids:
        if any([ns.scanpaths, ns.runtag, ns.start]):
            raise TypeError("HASH pathspec argument[s] incompatible with other pathspec arguments")
    if ns.runtag:
        if any([ns.scanpaths, ns.specids, ns.start]):
            raise TypeError(f"{ns.runtag}: argument incompatible with other pathspec arguments")
    if ns.scanpaths:
        if any([ns.runtag, ns.specids, ns.start]):
            raise TypeError("PATH argument[s] incompatible with other pathspec arguments")
    if ns.start:
        if any([ns.runtag, ns.specids, ns.scanpaths]):
            raise TypeError(f"{ns.start}: argument incompatible with other pathspec arguments")


class DeprecatedStoreAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        import warnings

        warnings.warn(
            f"{option_string} is deprecated and will be removed in a future release",
            category=UserWarning,
            stacklevel=2,
        )
        setattr(namespace, self.dest, values)


class WipeAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, False):
            return
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            return
        workspace.rmf()
        setattr(namespace, self.dest, True)
