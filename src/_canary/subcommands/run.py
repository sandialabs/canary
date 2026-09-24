# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary run`` subcommand for discovering and executing test suites."""

import argparse
import os
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Sequence

import yaml

from .. import config
from .. import rerun
from ..app.pathspec import RequestBuilder
from ..app.pathspec import RequestNode
from ..app.pathspec import ScanPathsRequest
from ..app.pathspec import TagRequest
from ..app.pathspec import classify_pathspec
from ..app.run import RunOptions
from ..app.run import run as app_run
from ..config.schemas import testpaths_schema
from ..generate import Generator
from ..plugins.hookspec import hookimpl
from ..select import Selector
from ..util import json_helper as json
from ..util.filesystem import working_dir
from ..util.rich import bold
from ..view import ViewSettings
from .base import CanarySubcommand
from .common import add_resource_arguments

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Run())


class Run(CanarySubcommand):
    """Find tests from a path specification, create a workspace if needed, and execute them.

    Supports scan-path, tag, spec-ID, and view-path request modes.  All filter,
    resource, and display-style options are also available.
    """

    name = "run"
    description = "Find and run tests from a pathspec"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        """Register all run arguments: paths, wipe, generator/selector options, style, view, etc."""
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
        parser.add_argument(
            "--empty-ok",
            action="store_true",
            default=False,
            help="Exit normally when the test set is empty.  "
            "By default, an empty test set is an error (exit code 7)",
        )

        parser.add_argument(
            "-s",
            "--style",
            dest="console_style",
            action=StyleAction,
            default={"name": "short", "live": True},
            help="Configure live console display style.  Given as key=value pairs:\n\n"
            "live={yes,no}[yes]: live console updating\n\n"
            "name={short,long}[short]: print short (default) names or long\n\n",
        )
        parser.add_argument(
            "--view",
            default=None,
            action=ViewAction,
            metavar=ViewAction.metavar,
            help=ViewAction.help_page(),
        )
        group = parser.add_argument_group("console reporting")
        group.add_argument("-e", action=DeprecatedStoreAction, help=argparse.SUPPRESS)
        group.add_argument("--capture", action=DeprecatedStoreAction, help=argparse.SUPPRESS)
        group.add_argument("--format", action=DeprecatedStoreAction, help=argparse.SUPPRESS)
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
        """Build the run request and options from *args* and delegate to ``app.run``."""
        request: RequestNode
        if req := getattr(args, "request", None):
            request = req
        else:
            request = TagRequest(value=config.get("run:default_tag"))
        if isinstance(request, TagRequest) and not request.value:
            request = TagRequest(value=config.get("run:default_tag"))

        view = ViewSettings(**args.view) if args.view else None
        options = RunOptions(
            tag=args.tag,
            on_options=args.on_options,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            owners=args.owners,
            regex=args.regex_filter,
            only=args.only,
            view=view,
            wipe_workspace=bool(args.wipe_workspace),
            work_tree=args.work_tree,
        )
        return app_run(request, options)


def setdefault(obj, attr, default):
    """Set *attr* on *obj* to *default* if absent or ``None``, then return its value."""
    if not hasattr(obj, attr):
        setattr(obj, attr, default)
    elif getattr(obj, attr) is None:
        setattr(obj, attr, default)
    return getattr(obj, attr)


class StyleAction(argparse.Action):
    """Parse ``--style key=value`` pairs into a console-style configuration dict."""

    style_choices = {"name": ("long", "short"), "live": ("yes", "no")}

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        style = getattr(namespace, self.dest, None) or {}
        key, sep, value = values.strip().partition("=")  # type: ignore
        if sep != "=":
            parser.error(f"Invalid format for {option_string}: {values!r}, expected key=value")
        if choices := self.style_choices.get(key):
            if value not in choices:
                parser.error(f"Invalid choice {value!r} for style config {key}")
        else:
            parser.error(f"Invalid style config {key!r}")
        if value in ("yes", "no"):
            style[key] = {"yes": True, "no": False}[value]
        else:
            style[key] = value
        setattr(namespace, self.dest, style)


class DeprecatedStoreAction(argparse.Action):
    """Emit a deprecation warning then store the value, for removed flags kept for compatibility."""

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
    """Record that the workspace should be wiped before running (``-w``).

    The wipe itself is performed by :func:`_canary.app.run.run` when it opens
    the workspace, so no filesystem access happens during argument parsing.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
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

        builder: RequestBuilder = setdefault(namespace, "request_builder", RequestBuilder())
        script_args: list[str] = setdefault(namespace, "script_args", [])

        # Split REMAINDER into script_args (after '--') and items
        for i, val in enumerate(values):
            if val == "--":
                script_args.extend(values[i + 1 :])
                values = values[:i]
                break

        # Classifying items against the workspace (tags/view paths/spec ids)
        # requires workspace access and is application logic, so it lives behind
        # the facade.  Errors are returned on the builder and re-raised here as a
        # usage error.
        classify_pathspec(list(values), builder=builder)

        if builder.errors:
            raise argparse.ArgumentError(self, "\n".join(builder.errors))

        request = builder.finalize()
        setattr(namespace, "request", request)
        setattr(namespace, "script_args", script_args)
        setattr(namespace, self.dest, values)

        # backward compat
        if isinstance(request, ScanPathsRequest):
            setattr(namespace, "scanpaths", request.value)

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
    canary run 7yral9i                     rerun test job with hash 7yral9i

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


class ViewAction(argparse.Action):
    """Parse ``--view key=value,...`` into a view-settings dict."""

    default_value = {"mode": "symlink", "only": "all", "when": "always"}
    metavar = "key=value"

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: Optional[str] = None,
    ) -> None:
        assert isinstance(values, str)
        choices = {
            "mode": {"symlink", "hardlink", "copy", "none"},
            "only": {"all", "failed", "not_pass", "passed"},
            "when": {"on_success", "on_failure", "always", "never"},
            "name": set(),
        }
        view = getattr(namespace, self.dest, None) or {
            "mode": "symlink",
            "only": "all",
            "when": "always",
            "name": "TestResults",
        }
        for value in values.split(","):
            if not value.split():
                continue
            section, _, arg = value.partition("=")
            if not arg:
                err = f"Expected {option_string} <section>=<value>, got {value}"
                raise argparse.ArgumentError(self, err)
            if section not in list(choices.keys()):
                s = ", ".join(choices.keys())
                raise argparse.ArgumentError(
                    self, f"Unknown view section {section!r}.  Choose from {s}"
                )
            if section != "name" and arg not in choices[section]:
                s = ", ".join(choices[section])
                raise argparse.ArgumentError(
                    self, f"Unknown view {section} {arg!r}.  Choose from {s}"
                )
            view[section] = arg
        setattr(namespace, self.dest, view)
        return

    @staticmethod
    def help_page() -> str:
        """Return the multi-line help text for the ``--view`` option."""
        return """Configure the results view. Given as comma separated key=value pairs:\n
• mode={symlink,hardlink,copy,none}[symlink]: how to create the view\n
• only={all,failed,not_pass,passed}[all]: which tests to include\n
• when={on_success,on_failure,always,never}[always]: when to create the view\n"""


class ReadPathsFromFile(argparse.Action):
    """Read scan paths from a YAML or JSON ``testpaths`` file and populate the request builder."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: Optional[str] = None,
    ) -> None:
        assert isinstance(values, str)
        builder: RequestBuilder = setdefault(namespace, "request_builder", RequestBuilder())
        builder.require_kind("scanpaths", f"file {values}")
        if builder.errors:
            raise argparse.ArgumentError(self, builder.errors[0])
        builder.scanpaths.update(self.read_paths(values))
        request = builder.finalize()
        setattr(namespace, "request", request)
        setattr(namespace, self.dest, values)
        # backward compat
        setattr(namespace, "scanpaths", None if request is None else request.value)
        return

    @staticmethod
    def read_paths(file: str) -> dict[str, list[str]]:
        """Parse a YAML or JSON testpaths file and return ``{abs_root: [rel_paths]}``."""
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
        """Return the help text for the ``-f`` pathspec-file option."""
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
