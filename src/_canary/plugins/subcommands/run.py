import argparse
import sys
from typing import TYPE_CHECKING

from ...third_party.color import colorize
from ...util import graph
from ...util import logging
from ...util.banner import banner
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Run()


class Run(CanarySubcommand):
    name = "run"
    description = "Find and run tests from a pathspec"

    def setup_parser(self, parser: "Parser") -> None:
        parser.epilog = "See canary help --pathspec for help on the path specification"
        add_work_tree_arguments(parser)
        add_filter_arguments(parser)
        group = parser.add_argument_group("console reporting")
        group.add_argument(
            "--no-header",
            action="store_true",
            default=False,
            help="Disable printing header [default: %(default)s]",
        )
        group.add_argument(
            "--no-summary",
            action="store_true",
            default=False,
            help="Disable summary [default: %(default)s]",
        )
        group.add_argument(
            "--durations",
            type=int,
            metavar="N",
            help="Show N slowest test durations (N=0 for all)",
        )
        group.add_argument("-r", help="Deprecated option.  Use -q or -v to adjust verbosity")
        parser.add_argument("-u", "--until", choices=("discover", "lock"), help=argparse.SUPPRESS)
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            default=False,
            help="Stop after first failed test [default: %(default)s]",
        )
        parser.add_argument(
            "-P",
            choices=("permissive", "pedantic"),
            default="pedantic",
            help="If pedantic (default), stop if file parsing errors occur, else ignore parsing errors",
        )
        parser.add_argument(
            "--no-reset",
            "--dont-restage",
            dest="dont_restage",
            action="store_true",
            default=False,
            help="Do not return the test execution directory "
            "to its original stage before re-running a test",
        )
        parser.add_argument(
            "--copy-all-resources",
            action="store_true",
            default=False,
            help="Do not link resources to the test directory, only copy [default: %(default)s]",
        )
        parser.add_argument(
            "--dont-measure",
            default=False,
            action="store_true",
            help="Do not collect a test's process information [default: %(default)s]",
        )
        add_resource_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        from ...session import Session

        if not args.no_header:
            logging.emit(banner() + "\n")
        PathSpec.parse(args)
        session: Session
        if args.mode == "w":
            path = args.work_tree or Session.default_worktree
            session = Session(path, mode=args.mode, force=args.wipe)
            session.add_search_paths(args.paths)
            session.discover(pedantic=args.P == "pedantic")
            if args.until is not None:
                generators = session.generators
                roots = set()
                for generator in generators:
                    roots.add(generator.root)
                n, N = len(generators), len(roots)
                s, S = "" if n == 1 else "s", "" if N == 1 else "s"
                logging.info(colorize("@*{Collected} %d file%s from %d root%s" % (n, s, N, S)))
                if args.until == "discover":
                    logging.info("Done with test discovery")
                    return 0
            session.lock(
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                on_options=args.on_options,
                env_mods=args.env_mods.get("test") or {},
                regex=args.regex_filter,
            )

            if args.until is not None:
                active_cases = session.get_ready()
                n, N = len(active_cases), len({case.file for case in active_cases})
                s, S = "" if n == 1 else "s", "" if N == 1 else "s"
                logging.info(colorize("@*{Expanded} %d case%s from %d file%s" % (n, s, N, S)))
                graph.print(active_cases, file=sys.stdout)
                if args.until == "lock":
                    logging.info("Done freezing test cases")
                    return 0

        elif args.mode == "a":
            session = Session(args.work_tree, mode=args.mode)
            session.filter(
                start=args.start,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                case_specs=getattr(args, "case_specs", None),
            )
        else:
            assert args.mode == "b"
            session = Session.batch_view(args.work_tree, args.batch_id)
        session.run(fail_fast=args.fail_fast)
        if not args.no_summary:
            logging.emit(session.summary(include_pass=False))
        if args.durations:
            logging.emit(session.durations(args.durations))
        logging.emit(session.footer())
        return session.exitstatus
