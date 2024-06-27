import argparse
import os
import sys
import traceback
from typing import TYPE_CHECKING

from ..error import StopExecution
from ..resources import ResourceHandler
from ..session import ExitCode
from ..session import Session
from ..test.case import TestCase
from ..third_party.color import colorize
from ..util import graph
from ..util import logging
from ..util.banner import banner
from .common import PathSpec
from .common import add_batch_arguments
from .common import add_mark_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Run the tests"


def setup_parser(parser: "Parser"):
    parser.epilog = PathSpec.description()
    add_work_tree_arguments(parser)
    add_mark_arguments(parser)
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
    group.add_argument(
        "-r",
        metavar="{b, v}",
        default="b",
        choices=("b", "v"),
        help="During test execution, show progress bar (``-rb``, default) or print each "
        "test case as it starts/finishes of every case (``-rv``)",
    )
    parser.add_argument(
        "-u", "--until", choices=("discover", "freeze", "populate"), help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Stop after first failed test [default: %(default)s]",
    )
    parser.add_argument(
        "--copy-all-resources",
        action="store_true",
        help="Do not link resources to the test directory, only copy [default: %(default)s]",
    )
    add_resource_arguments(parser)
    add_batch_arguments(parser)
    parser.add_argument(
        "pathspec",
        metavar="pathspec",
        nargs="*",
        help="Test file[s] or directories to search",
    )


def run(args: "argparse.Namespace") -> int:
    logging.emit(banner() + "\n")
    PathSpec.parse(args)
    session: Session
    cases: list[TestCase]
    if args.mode == "w":
        path = args.work_tree or Session.default_worktree
        session = Session(path, mode=args.mode, force=args.wipe)
        s = ", ".join(os.path.relpath(p, os.getcwd()) for p in args.paths) if args.paths else "."
        logging.emit(colorize("@*{searching} for tests in %s\n" % s))
        session.add_search_paths(args.paths)
        session.discover()
        if args.until is not None:
            generators = session.generators
            roots = set()
            for generator in generators:
                roots.add(generator.root)
            n, N = len(generators), len(roots)
            s, S = "" if n == 1 else "s", "" if N == 1 else "s"
            logging.info(colorize("@*{collected} %d file%s from %d root%s" % (n, s, N, S)))
            if args.until == "discover":
                logging.info("done with test discovery")
                return 0
        logging.emit(colorize("@*{generating} test cases from test files\n"))
        session.freeze(
            rh=args.rh,
            keyword_expr=args.keyword_expr,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
        )
        if args.until is not None:
            cases = [case for case in session.cases if not case.mask]
            n, N = len(cases), len([case.file for case in cases])
            s, S = "" if n == 1 else "s", "" if N == 1 else "s"
            logging.info(colorize("@*{expanded} %d case%s from %d file%s" % (n, s, N, S)))
            graph.print(cases, file=sys.stdout)
            if args.until == "freeze":
                logging.info("done freezing test cases")
                return 0
        if not args.no_header:
            logging.emit(session.overview(session.cases))
        session.populate(copy_all_resources=args.copy_all_resources)
        if args.until == "populate":
            logging.info("done populating worktree")
            return 0
        cases = [case for case in session.cases if case.status.satisfies(("pending", "ready"))]
    elif args.mode == "a":
        session = Session(args.work_tree, mode=args.mode)
        cases = session.filter(
            start=args.start,
            keyword_expr=args.keyword_expr,
            parameter_expr=args.parameter_expr,
            rh=args.rh,
        )
        if not args.batched_invocation and session.db.exists("batches/1"):
            # Reload batch info so that the tests can be rerun in the scheduler
            args.rh = args.rh or ResourceHandler()
            meta = session.db.load_json("batches/1/meta")
            for var, val in meta.items():
                if val is not None:
                    args.rh.set(f"batch:{var}", val)
        if not args.no_header:
            logging.emit(session.overview(cases))
    else:
        assert args.mode == "b"
        session = Session(args.work_tree, mode="a")
        cases = session.bfilter(lot_no=args.lot_no, batch_no=args.batch_no)
    output = {"b": "progress", "v": "verbose"}[args.r]
    try:
        session.exitstatus = session.run(
            cases,
            rh=args.rh,
            output=output,
            fail_fast=args.fail_fast,
        )
    except KeyboardInterrupt:
        session.exitstatus = ExitCode.INTERRUPTED
    except StopExecution as e:
        session.exitstatus = e.exit_code
    except TimeoutError:
        session.exitstatus = ExitCode.TIMEOUT
    except SystemExit as ex:
        session.exitstatus = ex.code if isinstance(ex.code, int) else 1
    except BaseException:
        session.exitstatus = ExitCode.INTERNAL_ERROR
        logging.fatal(traceback.format_exc())
    else:
        if not args.no_summary:
            logging.emit(session.summary(cases, include_pass=False))
        if args.durations:
            logging.emit(session.durations(cases, args.durations))
        logging.emit(session.footer(cases))
    return session.exitstatus
