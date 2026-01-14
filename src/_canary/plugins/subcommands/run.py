# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Sequence

import yaml

from ... import config
from ... import rerun
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
            action=ReadPathsFromFile,
            dest="f_pathspec",
            metavar="file",
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )
        Generator.setup_parser(parser)
        Selector.setup_parser(parser, tagged="optional")
        rerun.setup_parser(parser)
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
            "runpaths",
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
        try:
            workspace = Workspace.load(start=work_tree)
        except NotAWorkspaceError:
            workspace = Workspace.create(path=work_tree)
        f = workspace.logs_dir / "canary.0.log"
        h = logging.json_file_handler(f)
        logging.add_handler(h)
        # start, specids, runtag, and scanpaths are mutually exclusive
        specs: list["ResolvedSpec"]

        request = getattr(args, "request", None) or {
            "kind": "tag",
            "payload": config.get("selection:default_tag"),
        }
        if request["kind"] == "scanpaths":
            specs = workspace.create_selection(
                tag=args.tag,
                scanpaths=request["payload"],
                on_options=args.on_options,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        else:
            if request["kind"] == "specids":
                specids = request["payload"]
                workspace.db.resolve_spec_ids(specids)
                sids = [id[:7] for id in specids]
                if len(sids) > 3:
                    sids = [*sids[:2], "…", sids[-1]]
                logger.info(f"[bold]Running[/] {pluralize('spec', len(sids))} {', '.join(sids)}")
                specs = rerun.compute_rerun_closure(workspace.db, roots=specids)
                args.only = "all"
            elif request["kind"] == "viewpaths":
                logger.info("[bold]Running[/] tests from view paths")
                specs = rerun.get_specs_from_view(workspace.db, prefixes=request["payload"])
                args.only = "all"
            else:
                assert request["kind"] == "tag"
                tag = request["payload"]
                logger.info(f"[bold]Running[/] tests in tag {tag}")
                specs = rerun.get_specs(workspace.db, strategy=args.only, tag=tag)
            workspace.apply_selection_rules(
                specs,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        reuse = request.get("kind") == "viewpaths"
        session = workspace.run(specs, reuse_session=reuse, only=args.only or "not_pass")
        return session.returncode


def setdefault(obj, attr, default):
    if not hasattr(obj, attr):
        setattr(obj, attr, default)
    elif getattr(obj, attr) is None:
        setattr(obj, attr, default)
    return getattr(obj, attr)


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


class PathSpec(argparse.Action):
    """Parse the REMAINDER pathspec argument.

    Each entry can be one of:
    - scanpaths (file or directory to scan, or YAML/JSON testpaths file)
    - viewpaths (path inside a previous session view)
    - specids (test IDs)
    - runtag (test selection tag)
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: Optional[str] = None,
    ) -> None:
        assert isinstance(values, list)

        request: dict[str, Any] = setdefault(namespace, "request", {})
        script_args: list[str] = setdefault(namespace, "script_args", [])

        # Split REMAINDER into script_args (after '--') and items
        for i, val in enumerate(values):
            if val == "--":
                script_args.extend(values[i + 1 :])
                values = values[:i]
                break

        workspace: Workspace | None = None
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            pass

        errors: list[str] = []
        possible_specs: list[str] = []
        for item in values:
            abspath = os.path.abspath(item)

            # --- Lock file not supported ---
            if os.path.isfile(item) and item.endswith("testcases.lock"):
                errors.append(f"{item}: lock file scanning not implemented")
                continue

            # --- Tag ---
            if workspace and workspace.is_tag(item):
                if request.get("kind", "tag") != "tag":
                    errors.append(f"Cannot mix {request.get('kind')} with tag {item}")
                    continue
                request["kind"] = "tag"
                request["payload"] = item
                continue

            # --- View path ---
            if workspace and (rel_path := workspace.relative_to_view(abspath)):
                if request.get("kind", "viewpaths") != "viewpaths":
                    errors.append(f"Cannot mix {request.get('kind')} with viewpaths {abspath}")
                    continue
                request["kind"] = "viewpaths"
                p = rel_path if os.path.isfile(abspath) else rel_path.rstrip("/") + "/%"
                request.setdefault("payload", []).append(p)
                continue

            # --- Directory scanpaths ---
            if os.path.isdir(abspath):
                if request.get("kind", "scanpaths") != "scanpaths":
                    errors.append(f"Cannot mix {request.get('kind')} with scanpaths {abspath}")
                    continue
                request["kind"] = "scanpaths"
                request.setdefault("payload", {})[abspath] = []
                continue

            # --- File scanpaths ---
            elif os.path.isfile(abspath):
                if request.get("kind", "scanpaths") != "scanpaths":
                    errors.append(f"Cannot mix {request.get('kind')} with scanpaths {abspath}")
                    continue
                request["kind"] = "scanpaths"
                root, name = os.path.split(abspath)
                payload: dict[str, list[str]] = request.setdefault("payload", {})
                payload.setdefault(root, []).append(name)
                continue

            # --- Version control prefix ---
            if item.startswith(vc_prefixes):
                path_part = item.partition("@")[2]
                if not os.path.isdir(path_part):
                    errors.append(f"{path_part}: no such directory")
                    continue
                if request.get("kind", "scanpaths") != "scanpaths":
                    errors.append(f"Cannot mix {request.get('kind')} with scanpaths {item}")
                    continue
                request["kind"] = "scanpaths"
                payload = request.setdefault("payload", {})
                payload[item] = []
                continue

            # --- root:name style ---
            if os.pathsep in item and os.path.exists(item.replace(os.pathsep, os.path.sep)):
                if request.get("kind", "scanpaths") != "scanpaths":
                    errors.append(f"Cannot mix {request.get('kind')} with scanpaths {item}")
                    continue
                request["kind"] = "scanpaths"
                root, name = item.split(os.pathsep, 1)
                payload = request.setdefault("payload", {})
                payload.setdefault(os.path.abspath(root), []).append(
                    name.replace(os.pathsep, os.path.sep)
                )
                continue

            # --- Treat as possible test ID ---
            possible_specs.append(item)

        # --- Handle possible specs ---
        if possible_specs:
            if workspace is None:
                errors.append("Spec IDs require an active workspace")
            elif request.get("kind", "specids") != "specids":
                errors.append(f"Cannot mix {request.get('kind')} with specids")
            else:
                request["kind"] = "specids"
                found_ids: list[str | None] = workspace.find_specids(possible_specs)
                valid_ids: list[str] = []
                for i, fid in enumerate(found_ids):
                    if fid is None:
                        errors.append(f"{possible_specs[i]}: not a valid test identifier")
                    else:
                        valid_ids.append(fid)
                request.setdefault("payload", []).extend(valid_ids)
        if errors:
            raise argparse.ArgumentError(self, "\n".join(errors))

        setattr(namespace, "request", request)
        setattr(namespace, "script_args", script_args)
        setattr(namespace, self.dest, values)
        # backward compat
        if request["kind"] == "scanpaths":
            setattr(namespace, "scanpaths", request["payload"])

    @staticmethod
    def canary_help() -> str:
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


class ReadPathsFromFile(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: Optional[str] = None,
    ) -> None:
        assert isinstance(values, str)
        request: dict[str, Any] = setdefault(namespace, "request", {})
        if request.get("kind", "scanpaths") != "scanpaths":
            raise argparse.ArgumentError(
                self, f"Cannot mix {request.get('kind')} with file {values}"
            )
        request["kind"] = "scanpaths"
        request.setdefault("payload", {}).update(self.read_paths(values))
        setattr(namespace, "request", request)
        setattr(namespace, self.dest, values)
        # backward compat
        setattr(namespace, "scanpaths", request["payload"])
        return

    @staticmethod
    def read_paths(file: str) -> dict[str, list[str]]:
        data: dict
        if file.endswith(".json"):
            with open(file, "r") as fh:
                data = json.load(fh)
        else:
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
    def canary_help() -> str:
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
