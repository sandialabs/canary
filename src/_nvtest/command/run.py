import argparse
import os
import sys
import traceback

from _nvtest.config.argparsing import Parser
from _nvtest.error import StopExecution
from _nvtest.session import ExitCode
from _nvtest.session import ProgressReporting
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.third_party.color import colorize
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.banner import banner

from .base import Command
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments


class Run(Command):
    @property
    def description(self) -> str:
        return "Find and run tests from a pathspec"

    def setup_parser(self, parser: "Parser"):
        parser.epilog = PathSpec.description()
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
        group.add_argument(
            "-r",
            choices=("b", "v"),
            default="v",
            metavar="char",
            help="Test progress reporting as specified by char: "
            "(v)verbose: show start/finish/status of each test case as it occurs; "
            "(b)ar: show progress bar as tests progress. [default: v]",
        )
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
            help="If pedantic (default), stop if file parsing errors occur, "
            "else ignore parsing errors",
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
        parser.add_argument(
            "--stage",
            default=None,
            help="Run this execution stage [default: run]",
        )
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        logging.emit(banner() + "\n")
        PathSpec.parse(args)
        session: Session
        cases: list[TestCase]
        stage: str = args.stage or "run"
        if args.mode == "w":
            if stage != "run":
                raise ValueError("--stage must equal run when creating a new session")
            path = args.work_tree or Session.default_worktree
            session = Session(path, mode=args.mode, force=args.wipe)
            session.add_search_paths(args.paths)
            s = ", ".join(os.path.relpath(p, os.getcwd()) for p in session.search_paths)
            logging.info(colorize("@*{Searching} for tests in %s" % s))
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
            cases = session.lock(
                keyword_expr=args.keyword_expr,
                parameter_expr=args.parameter_expr,
                on_options=args.on_options,
                env_mods=args.env_mods.get("test") or {},
                regex=args.regex_filter,
            )
            if args.until is not None:
                unmasked_cases = [case for case in session.cases if not case.mask]
                n, N = len(unmasked_cases), len({case.file for case in unmasked_cases})
                s, S = "" if n == 1 else "s", "" if N == 1 else "s"
                logging.info(colorize("@*{Expanded} %d case%s from %d file%s" % (n, s, N, S)))
                graph.print(unmasked_cases, file=sys.stdout)
                if args.until == "lock":
                    logging.info("Done freezing test cases")
                    return 0
        elif args.mode == "a":
            session = Session(args.work_tree, mode=args.mode)
            cases = session.filter(
                start=args.start,
                keyword_expr=args.keyword_expr,
                parameter_expr=args.parameter_expr,
                stage=stage,
                case_specs=getattr(args, "case_specs", None),
            )
        else:
            assert args.mode == "b"
            session = Session(args.work_tree, mode="a")
            cases = session.bfilter(batch_id=args.batch_id)
        level = ProgressReporting.progress_bar if args.r == "b" else ProgressReporting.verbose
        reporting = ProgressReporting(level=level)
        try:
            session.exitstatus = session.run(
                cases, reporting=reporting, fail_fast=args.fail_fast, stage=stage
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
