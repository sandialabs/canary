import argparse
import os
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Optional
from typing import Sequence
from typing import Union

from .. import config
from .. import finder
from ..config.schemas import testpaths_schema
from ..error import StopExecution
from ..runner import valid_runners
from ..session import ExitCode
from ..session import Session
from ..test.status import Status
from ..test.testcase import TestCase
from ..util import tty
from ..util.filesystem import force_remove
from ..util.misc import partition
from ..util.time import time_in_seconds
from ..util.tty.color import colorize
from .common import add_mark_arguments
from .common import add_timing_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Run the tests"
epilog = """\
The behavior %(run)s is context dependent.

For %(new)s test sessions, the %(pathspec)s argument is scanned for test files to add
to the session.  %(pathspec)s can be one (or more) of the following types:
  - directory name:  the directory is recursively searched for test files ending in
    .vvt or .pyt (specific file extensions are configurable);
  - json or yaml file: file containing specific paths to tests and/or directories; and
  - .vvt or .pyt file: specific test files.

For %(existing)s test sessions, the %(pathspec)s argument is scanned for tests to rerun.
%(pathspec)s can be one (or more) of the following types:
  - directory name: run test files in this directory and its children;
  - test id: run this specific test, specified as %(id)s;
  - test file: run the test defined in this file; and
  - batch number: run this batch of tests, specified as %(batch_no)s.
""" % {
    "run": colorize("@*{nvtest run}"),
    "new": colorize("@*{new}"),
    "existing": colorize("@*{existing}"),
    "pathspec": colorize("@*{pathspec}"),
    "id": colorize("@*{/ID}"),
    "batch_no": colorize("@*{^BATCH_NO}"),
}


def setup_parser(parser: "Parser"):
    add_work_tree_arguments(parser)
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
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Stop after first failed test [default: %(default)s]",
    )
    parser.add_argument(
        "--execute-analysis-sections",
        action="store_true",
        default=False,
        help="Add --execute-analysis-sections to each test invocation, "
        "allowing tests to re-run analysis sections only [default: %(default)s]",
    )
    parser.add_argument(
        "--copy-all-resources",
        action="store_true",
        help="Do not link resources to the test "
        "directory, only copy [default: %(default)s]",
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
    group = parser.add_argument_group("batching")
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
        "pathspec",
        metavar="pathspec",
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


def run(args: "argparse.Namespace") -> int:
    parse_pathspec(args)
    initstate: int = 0

    timer = Timer()
    with timer.timeit("setup"):
        session = setup_session(args)
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
                execute_analysis_sections=args.execute_analysis_sections,
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
        session.exitstatus = ex.code if isinstance(ex.code, int) else 1
    except BaseException:
        session.exitstatus = ExitCode.INTERNAL_ERROR
    finally:
        if initstate >= 2:
            session.teardown()
    return session.exitstatus


def parse_pathspec(args: argparse.Namespace) -> None:
    """Parse the ``pathspec`` argument.

    The ``pathspec`` can take on different meanings, each entry in pathspec
    can represent one of

    - an input file containing search path information when creating a new session
    - a directory to search for test files when creating a new session
    - a filter when re-using a previous session
    - a batch number to run

    """
    args.start = None
    if config.get("session"):
        return _parse_in_session_pathspec(args)
    else:
        return _parse_new_session_pathspec(args)


def _parse_new_session_pathspec(args: argparse.Namespace) -> None:
    args.mode = "w"
    args.paths = {}
    if not args.pathspec:
        args.paths.setdefault(os.getcwd(), [])
        return
    for path in args.pathspec:
        if path.endswith((".yaml", ".yml", ".json")):
            read_paths(path, args.paths)
        elif os.path.isfile(path) and finder.is_test_file(path):
            root, name = os.path.split(path)
            args.paths.setdefault(root, []).append(name)
        elif os.path.isdir(path):
            args.paths.setdefault(path, [])
        else:
            tty.die(f"{path}: no such file or directory")


def _parse_in_session_pathspec(args: argparse.Namespace) -> None:
    assert config.get("session") is not None
    args.mode = "a"
    if args.work_tree is not None:
        tty.die(f"work_tree={args.work_tree} incompatible with path arguments")
    args.work_tree = config.get("session:work_tree")

    def setdefault(obj, attr, default):
        setattr(obj, attr, default)
        return getattr(obj, attr)

    pathspec: list[str] = []
    for i, p in enumerate(args.pathspec):
        if TestCase.spec_like(p):
            setdefault(args, "case_specs", []).append(p)
            args.pathspec[i] = None
        elif p.startswith("^"):
            args.mode = "b"
            setdefault(args, "batch_no", int(p[1:]))
        else:
            pathspec.append(p)
    if getattr(args, "case_specs", None):
        if pathspec:
            tty.die("do not mix /ID with other pathspec arguments")
    elif getattr(args, "batch_no", None):
        if pathspec:
            tty.die("do not mix ^BATCH with other pathspec arguments")
    if len(pathspec) > 1:
        tty.die("incompatible input path arguments")
    if args.wipe:
        tty.die("wipe=True incompatible with path arguments")
    if pathspec:
        path = os.path.abspath(pathspec.pop(0))
        if not os.path.exists(path):
            tty.die(f"{path}: no such file or directory")
        if path.endswith((".yaml", ".yml", ".json")):
            tty.die(f"path={path} is an illegal pathspec argument in re-use mode")
        if not path.startswith(args.work_tree):
            tty.die("path arg must be a child of the work tree")
        args.start = os.path.relpath(path, args.work_tree)
        if os.path.isfile(path):
            if finder.is_test_file(path):
                name = os.path.splitext(os.path.basename(path))[0]
                if args.keyword_expr:
                    args.keyword_expr += f" and {name}"
                else:
                    args.keyword_expr = name
            else:
                tty.die(f"{path}: unrecognized file extension")
        elif not args.keyword_expr:
            kwds: list[str] = []
            for f in os.listdir(path):
                if finder.is_test_file(f):
                    name = os.path.splitext(os.path.basename(f))[0]
                    kwds.append(name)
            args.keyword_expr = " and ".join(kwds)
    return


def print_front_matter(args: "argparse.Namespace"):
    n = N = config.get("machine:cpu_count")
    p = config.get("system:platform")
    v = config.get("python:version")
    tty.print(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}")
    if hasattr(args, "max_workers"):
        tty.print(f"Maximum subprocess workers: {args.max_workers or 'auto'}")
    tty.print(f"Working tree: {args.work_tree or Session.default_work_tree}")
    if args.mode == "w":
        paths = "\n  ".join(args.paths)
        tty.print(f"search paths:\n  {paths}")


def print_testcase_overview(
    cases: list[TestCase], duration: Optional[float] = None
) -> None:
    def unreachable(c):
        return c.status == "skipped" and c.status.details.startswith("Unreachable")

    files = {case.file for case in cases}
    _, cases = partition(cases, lambda c: unreachable(c))
    t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
    if duration is not None:
        t += "@*{ in %.2fs.}" % duration
    tty.print(colorize(t))
    cases_to_run = [case for case in cases if case.status == "staged"]
    files = {case.file for case in cases_to_run}
    t = "@*g{running} %d test cases from %d files" % (len(cases_to_run), len(files))
    tty.print(colorize(t))
    skipped = [case for case in cases if case.status == "skipped" or case.masked]
    skipped_reasons: dict[str, int] = {}
    for case in skipped:
        reason = case.mask if case.masked else case.status.details
        assert isinstance(reason, str)
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
    tty.print(colorize("@*b{skipping} %d test cases" % len(skipped)))
    reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
    for reason in reversed(reasons):
        tty.print(f"  • {skipped_reasons[reason]} {reason.lstrip()}")
    return


def cformat(case: TestCase) -> str:
    id = tty.color.colorize("@*b{%s}" % case.id[:7])
    if case.masked:
        string = "@*c{EXCLUDED} %s %s: %s" % (id, case.pretty_repr(), case.mask)
        return tty.color.colorize(string)
    string = "%s %s %s" % (case.status.cname, id, case.pretty_repr())
    if case.duration > 0:
        string += " (%.2fs.)" % case.duration
    elif case.status == "skipped":
        string += ": Skipped due to %s" % case.status.details
    return string


def print_testcase_results(
    cases: list[TestCase], duration: float = -1, durations: Optional[int] = None
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
        if case.masked:
            totals.setdefault("masked", []).append(case)
        else:
            totals.setdefault(case.status.iid, []).append(case)

    nonpass = ("skipped", "failed", "diffed", "timeout")
    level = tty.get_log_level()
    if level > tty.INFO and len(totals):
        tty.print("Short test summary info", centered=True)
    elif any(r in totals for r in nonpass):
        tty.print("Short test summary info", centered=True)
    if level > tty.VERBOSE and "masked" in totals:
        for case in totals["masked"]:
            tty.print(cformat(case))
    if level > tty.INFO:
        for status in ("staged", "success"):
            if status in totals:
                for case in totals[status]:
                    tty.print(cformat(case))
    for status in nonpass:
        if status in totals:
            for case in totals[status]:
                tty.print(cformat(case))

    summary_parts = []
    for member in Status.colors:
        n = len(totals.get(member, []))
        if n:
            c = Status.colors[member]
            stat = totals[member][0].status.name
            summary_parts.append(colorize("@%s{%d %s}" % (c, n, stat.lower())))
    text = ", ".join(summary_parts)
    tty.print(text + f" in {duration:.2f}s.", centered=True)


def print_durations(cases: list[TestCase], N: int) -> None:
    cases = [case for case in cases if case.duration > 0]
    sorted_cases = sorted(cases, key=lambda x: x.duration)
    if N > 0:
        sorted_cases = sorted_cases[-N:]
    tty.print(f"Slowest {len(sorted_cases)} durations", centered=True)
    for case in sorted_cases:
        tty.print("  %6.2f     %s" % (case.duration, case.pretty_repr()))


def read_paths(file: str, paths: dict[str, list[str]]) -> None:
    import yaml

    with open(file, "r") as fh:
        data = yaml.safe_load(fh)
    testpaths_schema.validate(data)
    for p in data["testpaths"]:
        if isinstance(p, str):
            paths.setdefault(p, [])
        else:
            paths.setdefault(p["root"], []).extend(p["paths"])


def setup_session(args: "argparse.Namespace") -> Session:
    if args.wipe:
        if args.mode != "w":
            tty.die(f"Cannot wipe work directory with mode={args.mode}")
        force_remove(args.work_tree or Session.default_work_tree)
    if not args.no_header:
        print_front_matter(args)
    session: Session
    if args.mode == "w":
        tty.print("Setting up test session", centered=True)
        if args.execute_analysis_sections:
            tty.die(
                "--execute-analysis-sections: "
                "option invalid with creation of new test session"
            )
        bc = Session.BatchConfig(size_t=args.batch_size, size_n=args.batches)
        session = Session.create(
            work_tree=args.work_tree or Session.default_work_tree,
            search_paths=args.paths,
            max_cores_per_test=args.max_cores_per_test,
            max_workers=args.max_workers,
            keyword_expr=args.keyword_expr,
            on_options=args.on_options,
            batch_config=bc,
            parameter_expr=args.parameter_expr,
            copy_all_resources=args.copy_all_resources,
        )
    elif args.mode == "b":
        session = Session.load_batch(batch_no=args.batch_no)
    else:
        assert args.mode == "a"
        tty.print("Setting up test session", centered=True)
        session = Session.load(mode=args.mode)
        session.filter(
            keyword_expr=args.keyword_expr,
            start=args.start,
            parameter_expr=args.parameter_expr,
            max_cores_per_test=args.max_cores_per_test,
            case_specs=getattr(args, "case_specs", None),
        )
    session.exitstatus = ExitCode.OK
    return session
