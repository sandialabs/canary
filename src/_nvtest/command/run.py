import argparse
import glob
import os
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Optional
from typing import Sequence
from typing import Union

from ..config import Config
from ..error import StopExecution
from ..runner import valid_runners
from ..schemas import testpaths_schema
from ..session import ExitCode
from ..session import Session
from ..test.enums import Result
from ..test.enums import Skip
from ..test.testcase import TestCase
from ..util import tty
from ..util.filesystem import force_remove
from ..util.time import time_in_seconds
from ..util.tty.color import colorize
from .common import add_mark_arguments
from .common import add_timing_arguments
from .common import add_workdir_arguments

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Run the tests"


def setup_parser(parser: "Parser"):
    parser.prefix_chars = "-^"
    add_workdir_arguments(parser)
    add_mark_arguments(parser)
    add_timing_arguments(parser)
    group = parser.add_argument_group("console reporting")
    group.add_argument(
        "--no-header",
        action="store_true",
        default=False,
        help="Disable header [default: %(default)s]",
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
    parser.add_argument(
        "-u",
        "--until",
        choices=("setup", "run", "postrun"),
        help="Stage to stop after when testing [default: %(default)s]",
    )
    group = parser.add_argument_group("resource control")
    group.add_argument(
        "-N",
        "--max-cores-per-test",
        type=int,
        metavar="N",
        default=None,
        help="Skip tests requiring more than N cores.  For direct runs, N is set to "
        "the number of available cores",
    )
    group.add_argument(
        "-n",
        "--max-workers",
        type=int,
        metavar="N",
        default=None,
        help="Execute tests/batches asynchronously using a pool of at most "
        "N workers.  For batched runs, the default is 5.  For direct runs, the "
        "max_workers is determined automatically",
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
        help="Do not link resources to the test "
        "directory, only copy [default: %(default)s]",
    )
    group = parser.add_argument_group("batching")
    group.add_argument("^s", dest="session_no", type=int, help=argparse.SUPPRESS)
    group.add_argument("^b", dest="batch_no", type=int, help=argparse.SUPPRESS)
    p1 = group.add_mutually_exclusive_group()
    p1.add_argument(
        "--batch-size",
        metavar="T",
        type=time_in_seconds,
        default=None,
        help="Batch size in seconds (accepts human readable times, "
        "eg 1s, 1 sec, 1h, 2 hrs, etc) [default: 30m]",
    )
    p1.add_argument(
        "--batches",
        metavar="N",
        type=int,
        default=None,
        help="Number of batches.  Batches will be populated such that their run "
        "times are approximately the same",
    )
    group.add_argument(
        "--runner",
        default="direct",
        choices=valid_runners,
        help="Work load manager [default: %(default)s]",
    )
    help_msg = colorize(
        "Pass @*{option} as an option to the runner. "
        "If @*{option} contains commas, it is split into multiple options at the "
        "commas. You can use this syntax to pass an argument to the runner. "
        "For example, -R,-A,XXXX passes -A XXXX to the runner."
    )
    group.add_argument(
        "-R",
        action=RunnerOptions,
        dest="runner_options",
        metavar="option",
        help=help_msg,
    )
    parser.add_argument(
        "path_args",
        metavar="file_or_dir",
        nargs="*",
        help="Test file[s] or directories to search",
    )


class RunnerOptions(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        runner_opts: list[str] = getattr(namespace, self.dest, None) or []
        assert isinstance(option, str)
        options: list[str] = option.replace(",", " ").split()
        runner_opts.extend(options)
        setattr(namespace, self.dest, runner_opts)


class Timer:
    T0: int = 111
    TF: int = 222

    def __init__(self):
        self.data = {}

    @contextmanager
    def timeit(self, label: str) -> Generator[None, None, None]:
        try:
            start = time.time()
            yield
        finally:
            finish = time.time()
            self.data[label] = {self.T0: start, self.TF: finish}

    def duration(self, label: str) -> float:
        return self.data[label][self.TF] - self.data[label][self.T0]


def run(config: "Config", args: "argparse.Namespace") -> int:
    parse_user_paths(args)
    initstate: int = 0

    timer = Timer()
    with timer.timeit("setup"):
        session = setup_session(config, args)
    setup_duration = timer.duration("setup")

    initstate = 1
    try:
        if not args.no_header:
            print_testcase_overview(session.cases, duration=setup_duration)
        if args.until == "setup":
            return 0
        tty.print("Beginning test session", centered=True)
        initstate = 2
        with timer.timeit("run"):
            session.exitstatus = session.run(
                timeout=args.timeout,
                runner=args.runner,
                runner_options=args.runner_options,
                fail_fast=args.fail_fast,
            )
        run_duration = timer.duration("run")
        if not args.no_summary:
            print_testcase_results(
                session.queue.cases, duration=run_duration, durations=args.durations
            )
        if args.until == "run":
            return session.exitstatus
    except KeyboardInterrupt:
        session.exitstatus = ExitCode.INTERRUPTED
    except StopExecution as e:
        session.exitstatus = e.exit_code
    except TimeoutError:
        session.exitstatus = ExitCode.TIMEOUT
    except SystemExit as ex:
        session.exitstatus = ex.code
    except BaseException:
        session.exitstatus = ExitCode.INTERNAL_ERROR
    finally:
        if initstate >= 2:
            session.teardown()
    return session.exitstatus


def parse_user_paths(args: argparse.Namespace) -> None:

    workdir = args.workdir
    wipe = args.wipe

    mode = start = None
    paths: dict[str, list[str]] = {}
    if args.batch_no:
        # if a specific batch number is given, then nvtest is being called
        # recursively and the positional argument is the work directory
        assert len(args.path_args) == 1
        if args.session_no is None:
            raise ValueError(f"^b{args.batch_no} requires ^sSESSION_ID")
        if workdir is not None:
            raise ValueError(f"^b{args.batch_no} and -d{args.workdir} are incompatible")
        mode = "b"
        workdir = args.path_args.pop(0)
        assert len(args.path_args) == 0
    for path in args.path_args:
        if Session.is_workdir(path, ascend=True):
            mode = "a"
            if len(args.path_args) > 1:
                raise ValueError("incompatible input path arguments")
            if workdir is not None:
                raise ValueError(f"workdir={path} incompatible with path arguments")
            if wipe:
                raise ValueError("wipe=True incompatible with path arguments")
            workdir = Session.find_workdir(path)
            start = os.path.relpath(path, workdir)
            if path.endswith((".vvt", ".pyt")):
                args.keyword_expr = os.path.splitext(os.path.basename(path))[0]
            else:
                for ext in (".vvt", ".pyt"):
                    f = glob.glob(f"{path}/*{ext}")
                    if len(f) == 1:
                        args.keyword_expr = os.path.splitext(os.path.basename(f[0]))[0]
                        break
        elif path.endswith((".yaml", ".yml", ".json")):
            mode = "w"
            read_paths(path, paths)
        elif os.path.isfile(path) and path.endswith((".vvt", ".pyt")):
            mode = "w"
            root, name = os.path.split(path)
            paths.setdefault(root, []).append(name)
        elif os.path.isdir(path):
            mode = "w"
            paths.setdefault(path, [])
        else:
            raise ValueError(f"{path}: no such file or directory")

    assert mode is not None
    args.start = start
    args.paths = paths
    args.mode = mode
    args.workdir = workdir


def print_front_matter(config: "Config", args: "argparse.Namespace"):
    n = N = config.machine.cpu_count
    p = config.machine.platform
    v = config.python.version
    tty.print(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}")
    if hasattr(args, "max_workers"):
        tty.print(f"Maximum subprocess workers: {args.max_workers or 'auto'}")
    tty.print(f"Test results directory: {args.workdir or Session.default_workdir}")
    if args.mode == "w":
        paths = "\n  ".join(args.paths)
        tty.print(f"search paths:\n  {paths}")


def print_testcase_overview(
    cases: list[TestCase], duration: Optional[float] = None
) -> None:
    cases = [case for case in cases if case.skip.reason != Skip.UNREACHABLE]
    files = {case.file for case in cases}
    t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
    if duration is not None:
        t += "@*{ in %.2fs.}" % duration
    tty.print(colorize(t))
    cases_to_run = [case for case in cases if not case.skip]
    files = {case.file for case in cases_to_run}
    t = "@*g{running} %d test cases from %d files" % (len(cases_to_run), len(files))
    tty.print(colorize(t))
    skipped = [case for case in cases if case.skip]
    skipped_reasons: dict[str, int] = {}
    for case in skipped:
        reason = case.skip.reason
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
    tty.print(colorize("@*b{skipping} %d test cases" % len(skipped)))
    reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
    for reason in reversed(reasons):
        tty.print(f"  • {skipped_reasons[reason]} {reason.lstrip()}")
    return


def print_testcase_results(
    cases: list[TestCase], duration: float = -1, durations: int = None
) -> None:

    if not cases:
        tty.info("Nothing to report")
        return

    if durations is not None:
        print_durations(cases, int(durations))

    if duration == -1:
        finish = max(_.finish for _ in cases)
        start = min(_.start for _ in cases)
        duration = finish - start

    totals: dict[str, list[TestCase]] = {}
    for case in cases:
        totals.setdefault(case.result.name, []).append(case)

    nonpass = (Result.FAIL, Result.DIFF, Result.SKIP, Result.NOTDONE)
    level = tty.get_log_level()
    if level > tty.INFO and len(totals):
        tty.print("Short test summary info", centered=True)
    elif any(r in totals for r in nonpass):
        tty.print("Short test summary info", centered=True)
    if level > tty.VERBOSE and Result.NOTRUN in totals:
        for case in totals[Result.NOTRUN]:
            tty.print("%s %s" % (case.result.cname, str(case)))
    if level > tty.INFO and Result.SETUP in totals:
        for case in totals[Result.SETUP]:
            tty.print("%s %s" % (case.result.cname, str(case)))
    if level > tty.INFO and Result.PASS in totals:
        for case in totals[Result.PASS]:
            tty.print("%s %s" % (case.result.cname, str(case)))

    nreported = 0
    for result in (Result.FAIL, Result.DIFF, Result.TIMEOUT):
        if result not in totals:
            continue
        for case in totals[result]:
            f = case.logfile
            if f.startswith(os.getcwd()):
                f = os.path.relpath(f)
            reasons = [case.result.reason]
            if not case.result.reason and not os.path.exists(f):
                reasons.append("No log file found")
            else:
                reasons.append(f"See {f}")
            reason = ". ".join(_ for _ in reasons if _.split())
            tty.print("%s %s: %s" % (case.result.cname, str(case), reason))
            nreported += 1
    if Result.NOTDONE in totals:
        for case in totals[Result.NOTDONE]:
            tty.print("%s %s" % (case.result.cname, str(case)))
    if Result.SKIP in totals:
        for case in totals[Result.SKIP]:
            cname = case.result.cname
            reason = case.skip.reason
            tty.print("%s %s: Skipped due to %s" % (cname, str(case), reason))

    summary_parts = []
    for member in Result.members:
        if level <= tty.INFO and member == Result.NOTRUN:
            continue
        n = len(totals.get(member, []))
        if n:
            c = Result.colors[member]
            summary_parts.append(colorize("@%s{%d %s}" % (c, n, member.lower())))
    text = ", ".join(summary_parts)
    tty.print(text + f" in {duration:.2f}s.", centered=True)


def print_durations(cases: list[TestCase], N: int) -> None:
    cases = [case for case in cases if case.duration > 0]
    sorted_cases = sorted(cases, key=lambda x: x.duration)
    if N > 0:
        sorted_cases = sorted_cases[-N:]
    tty.print(f"Slowest {len(sorted_cases)} durations", centered=True)
    for case in sorted_cases:
        tty.print("%6.2f     %s" % (case.duration, str(case)))


def read_paths(file: str, paths: dict[str, list[str]]) -> None:
    import yaml

    with open(file, "r") as fh:
        data = yaml.safe_load(fh)
    testpaths_schema.validate(data)
    for p in data["testpaths"]:
        paths.setdefault(p["root"], []).extend(p["paths"])


def setup_session(config: "Config", args: "argparse.Namespace") -> Session:
    if args.wipe:
        if args.mode != "w":
            tty.die(f"Cannot wipe work directory with mode={args.mode}")
        force_remove(args.workdir or Session.default_workdir)
    if not args.no_header:
        print_front_matter(config, args)

    session: Session
    if args.mode == "w":
        tty.print("Setting up test session", centered=True)
        bc = Session.BatchConfig(size_t=args.batch_size, size_n=args.batches)
        session = Session.create(
            workdir=args.workdir or Session.default_workdir,
            search_paths=args.paths,
            config=config,
            max_cores_per_test=args.max_cores_per_test,
            max_workers=args.max_workers,
            keyword_expr=args.keyword_expr,
            on_options=args.on_options,
            batch_config=bc,
            parameter_expr=args.parameter_expr,
            copy_all_resources=args.copy_all_resources,
        )
    elif args.mode == "b":
        # Run a single batch
        assert args.batch_no is not None
        assert args.session_no is not None
        tty.print(f"Setting up batch {args.batch_no}", centered=True)
        session = Session.load_batch(
            workdir=args.workdir, batch_no=args.batch_no, session_no=args.session_no
        )
    else:
        assert args.mode == "a"
        tty.print("Setting up test session", centered=True)
        session = Session.copy(workdir=args.workdir, config=config, mode=args.mode)
        session.filter(
            keyword_expr=args.keyword_expr,
            start=args.start,
            parameter_expr=args.parameter_expr,
            max_cores_per_test=args.max_cores_per_test,
        )
    session.exitstatus = ExitCode.OK
    return session
