import argparse
import json
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
from ..runner import valid_schedulers
from ..session import REUSE_SCHEDULER
from ..session import ExitCode
from ..session import Session
from ..session import default_batchsize
from ..test.status import Status
from ..test.testcase import TestCase
from ..util import logging
from ..util import tty
from ..util.color import colorize
from ..util.filesystem import force_remove
from ..util.misc import partition
from .common import add_mark_arguments
from .common import add_resource_arguments
from .common import add_timing_arguments
from .common import add_work_tree_arguments
from .common import set_default_resource_args
from .common import setdefault

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Run the tests"


def setup_parser(parser: "Parser"):
    parser.add_argument(
        "-H",
        "--help-topic",
        action=ExtraHelpTopic,
        metavar=ExtraHelpTopic.metavar,
        dest="help_topic",
        help="Request extra help on topic",
    )
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
    parser.add_argument("-u", "--until", choices=("setup",), help=argparse.SUPPRESS)
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Stop after first failed test [default: %(default)s]",
    )
    parser.add_argument(
        "--copy-all-resources",
        action="store_true",
        help="Do not link resources to the test " "directory, only copy [default: %(default)s]",
    )

    add_resource_arguments(parser)

    group = parser.add_argument_group("batch scheduling options")
    group.add_argument(
        "--scheduler",
        default=None,
        choices=valid_schedulers,
        help="Work load manager [default: %(default)s]",
    )
    help_msg = colorize(
        "Pass @*{option} as an option to the scheduler. "
        "If @*{option} contains commas, it is split into multiple options at the "
        "commas. You can use this syntax to pass an argument to the scheduler. "
        "For example, -R,-A,XXXX passes -A XXXX to the scheduler."
    )
    group.add_argument(
        "-R",
        action=SchedulerOptions,
        dest="scheduler_options",
        metavar="option",
        help=help_msg,
    )
    parser.add_argument(
        "pathspec",
        metavar="pathspec",
        nargs="*",
        help="Test file[s] or directories to search",
    )


class SchedulerOptions(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        scheduler_opts: list[str] = getattr(namespace, self.dest, None) or []
        assert isinstance(option, str)
        options: list[str] = self.split_on_comma(option)
        scheduler_opts.extend(options)
        setattr(namespace, self.dest, scheduler_opts)

    @staticmethod
    def split_on_comma(string: str) -> list[str]:
        if not string:
            return []
        single_quote = "'"
        double_quote = '"'
        args: list[str] = []
        tokens = iter(string[1:] if string[0] == "," else string)
        arg = ""
        quoted = None
        while True:
            try:
                token = next(tokens)
            except StopIteration:
                args.append(arg)
                break
            if not quoted and token == ",":
                args.append(arg)
                arg = ""
                continue
            else:
                arg += token
            if token in (single_quote, double_quote):
                if quoted is None:
                    # starting a quoted string
                    quoted = token
                elif token == quoted:
                    # ending a quoted string
                    quoted = None
        return args


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
    if args.help_topic:
        ExtraHelpTopic.print(args.help_topic)
        return 0
    set_default_resource_args(args)
    parse_pathspec(args)
    initstate: int = 0

    timer = Timer()
    with timer.timeit("setup"):
        session = setup_session(args)
    if not args.no_header:
        print_front_matter(session)
    setup_duration = timer.duration("setup")

    initstate = 1
    try:
        if not args.no_header:
            print_testcase_overview(session.cases, duration=setup_duration)
        if args.until == "setup":
            logging.info("Stopping after setup (--until='setup')")
            return 0
        tty.print("Beginning test session", centered=True)
        initstate = 2
        with timer.timeit("run"):
            session.exitstatus = session.run(
                timeout=args.timeout,
                fail_fast=args.fail_fast,
            )
        run_duration = timer.duration("run")
        if not args.no_summary:
            print_testcase_results(
                session.queue.cases, duration=run_duration, durations=args.durations
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
    on_options: list[str] = []
    pathspec: list[str] = []
    for item in args.pathspec:
        if item.startswith("+"):
            on_options.append(item[1:])
        else:
            pathspec.append(item)
    args.pathspec = pathspec
    args.on_options.extend(on_options)
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
        if os.path.exists(path) and path.endswith((".yaml", ".yml", ".json")):
            read_paths(path, args.paths)
        elif os.path.isfile(path) and finder.is_test_file(path):
            root, name = os.path.split(path)
            args.paths.setdefault(root, []).append(name)
        elif os.path.isdir(path):
            args.paths.setdefault(path, [])
        elif os.pathsep in path and os.path.exists(path.replace(os.pathsep, os.path.sep)):
            # allow specifying as root:name
            root, name = path.split(os.pathsep, 1)
            args.paths.setdefault(root, []).append(name.replace(os.pathsep, os.path.sep))
        else:
            tty.die(f"{path}: no such file or directory")


def _parse_in_session_pathspec(args: argparse.Namespace) -> None:
    assert config.get("session") is not None
    args.mode = "a"
    if args.work_tree is not None:
        tty.die(f"work_tree={args.work_tree} incompatible with path arguments")
    args.work_tree = config.get("session:work_tree")

    pathspec: list[str] = []
    for i, p in enumerate(args.pathspec):
        if TestCase.spec_like(p):
            setdefault(args, "case_specs", []).append(p)
            args.pathspec[i] = None
        elif p.startswith("^"):
            args.mode = "b"
            batch_store, batch_no = [int(_) for _ in p[1:].split(":")]
            setdefault(args, "batch_no", batch_no)
            setdefault(args, "batch_store", batch_store)
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


def print_front_matter(session: "Session"):
    p = config.get("system:os:name")
    v = config.get("python:version")
    tty.print(f"{p} -- Python {v}")
    tty.print(f"Available cpus: {session.avail_cpus}")
    tty.print(f"Available cpus per test: {session.avail_cpus_per_test}")
    if session.avail_devices:
        tty.print(f"Available devices: {session.avail_devices}")
        tty.print(f"Available devices per test: {session.avail_devices_per_test}")
    tty.print(f"Maximum number of asynchronous jobs: {session.avail_workers}")
    tty.print(f"Working tree: {session.work_tree}")
    if session.mode == "w":
        paths = "\n  ".join(session.search_paths)
        tty.print(f"search paths:\n  {paths}")


def print_testcase_overview(cases: list[TestCase], duration: Optional[float] = None) -> None:
    def unreachable(c):
        return c.status == "skipped" and c.status.details.startswith("Unreachable")

    files = {case.file for case in cases}
    _, cases = partition(cases, lambda c: unreachable(c))
    t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
    if duration is not None:
        t += "@*{ in %.2fs.}" % duration
    tty.print(colorize(t))
    cases_to_run = [case for case in cases if not case.masked and not case.skipped]
    files = {case.file for case in cases_to_run}
    t = "@*g{running} %d test cases from %d files" % (len(cases_to_run), len(files))
    tty.print(colorize(t))
    skipped = [case for case in cases if case.skipped or case.masked]
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
    id = colorize("@*b{%s}" % case.id[:7])
    if case.masked:
        string = "@*c{EXCLUDED} %s %s: %s" % (id, case.pretty_repr(), case.mask)
        return colorize(string)
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
        logging.info("Nothing to report")
        return

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

    nonpass = ("skipped", "diffed", "timeout", "failed")
    level = logging.get_level()
    if level < logging.INFO and len(totals):
        tty.print("Short test summary info", centered=True)
    elif any(r in totals for r in nonpass):
        tty.print("Short test summary info", centered=True)
    if level < logging.DEBUG and "masked" in totals:
        for case in sorted(totals["masked"], key=lambda t: t.name):
            tty.print(cformat(case))
    if level < logging.INFO:
        for status in ("staged", "success"):
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    tty.print(cformat(case))
    for status in nonpass:
        if status in totals:
            for case in sorted(totals[status], key=lambda t: t.name):
                tty.print(cformat(case))

    if durations is not None:
        print_durations(cases, int(durations))

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
    data: dict
    if file.endswith(".json"):
        with open(file, "r") as fh:
            data = json.load(fh)
    else:
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
    session: Session
    if args.mode == "w":
        tty.print("Setting up test session", centered=True)
        if args.scheduler is not None:
            if args.batch_count is None and args.batch_time is None:
                args.batch_time = default_batchsize
        if args.batch_count is not None or args.batch_time is not None:
            if args.scheduler is None:
                raise ValueError("batch count and time require a scheduler argument")
            if args.workers_per_session is None:
                args.workers_per_session = 5
        session = Session.create(
            work_tree=args.work_tree or Session.default_work_tree,
            search_paths=args.paths,
            avail_cpus=args.cpus_per_session,
            avail_cpus_per_test=args.cpus_per_test,
            avail_devices=args.devices_per_session,
            avail_devices_per_test=args.devices_per_test,
            avail_workers=args.workers_per_session,
            keyword_expr=args.keyword_expr,
            on_options=args.on_options,
            parameter_expr=args.parameter_expr,
            batch_count=args.batch_count,
            batch_time=args.batch_time,
            scheduler=args.scheduler,
            scheduler_options=args.scheduler_options,
            copy_all_resources=args.copy_all_resources,
        )
    else:
        assert args.mode in "ba"
        session = Session.load(mode="a")
        if args.cpus_per_session is not None:
            session.avail_cpus = args.cpus_per_session
        if args.cpus_per_test is not None:
            session.avail_cpus_per_test = args.cpus_per_test
        if args.devices_per_session is not None:
            session.avail_devices = args.devices_per_session
        if args.devices_per_test is not None:
            session.avail_devices_per_test = args.devices_per_test
        if args.workers_per_session is not None:
            session.avail_workers = args.workers_per_session
        if args.mode == "b":
            session.filter(batch_no=args.batch_no, batch_store=args.batch_store)
        else:
            scheduler = None
            session.filter(
                keyword_expr=args.keyword_expr,
                start=args.start,
                parameter_expr=args.parameter_expr,
                avail_cpus_per_test=args.cpus_per_test,
                avail_devices_per_test=args.devices_per_test,
                case_specs=getattr(args, "case_specs", None),
            )
            if session.ini_options.get("scheduler"):
                scheduler = REUSE_SCHEDULER
        session.setup_runner(scheduler=scheduler)
    session.exitstatus = ExitCode.OK
    return session


def bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)


class ExtraHelpTopic(argparse.Action):
    choices = ("pathspec", "resource")
    metavar = "{%s}" % ",".join(choices)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        assert isinstance(option, str)
        if option in ("path", "pathspec"):
            topic = "pathspec"
        elif option in ("resource", "resources"):
            topic = "resource management"
        else:
            choices = ", ".join(self.choices)
            parser.error(f"invalid choice {option!r} (choose from {choices})")
        setattr(namespace, self.dest, topic)

    @staticmethod
    def print(topic: str) -> None:
        if topic == "pathspec":
            ExtraHelpTopic.print_pathspec_help()
        elif topic == "resource management":
            ExtraHelpTopic.print_resource_help()

    @staticmethod
    def print_pathspec_help() -> None:
        pathspec_help = """\
%(title)s

The behavior %(run)s is context dependent.

For %(new)s test sessions, the %(pathspec)s argument is scanned for test files to add
to the session.  %(pathspec)s can be one (or more) of the following types:

- directory name:  the directory is recursively searched for test files ending in
  .vvt or .pyt (specific file extensions are configurable);
- .vvt or .pyt file: specific test files; and
- json or yaml file: file containing specific paths to tests and/or directories.

The json input file has the following schema:

{
  "testpaths": [
    {
      "root": str,
      "paths": list_of_str
    }
  ]
}

where %(paths)s is a list of file paths relative to %(root)s.

For %(existing)s test sessions, the %(pathspec)s argument is scanned for tests to rerun.
%(pathspec)s can be one (or more) of the following types:

- directory name: run test files in this directory and its children;
- test id: run this specific test, specified as %(id)s;
- test file: run the test defined in this file; and
- batch number: run this batch of tests, specified as %(batch_no)s.
""" % {
            "title": bold("The pathspec argument"),
            "run": bold("nvtest run"),
            "new": bold("new"),
            "existing": bold("existing"),
            "pathspec": bold("pathspec"),
            "id": bold("/ID"),
            "batch_no": bold("^BATCH_NO"),
            "paths": bold("paths"),
            "root": bold("root"),
        }
        print(pathspec_help)

    @staticmethod
    def print_resource_help():
        resource_help = """\
%(title)s

The %(r_arg)s argument is of the form: %(r_form)s, where %(r_scope)s
(optional) is one of session, test, or batch, (session is assumed if not provided);
%(r_type)s is one of workers, cpus, or devices; and %(r_value)s is an integer value. By
default, nvtest will determine and all available cpu cores.

%(examples)s
- -l test:cpus:5: Skip tests requiring more than 5 cpu cores.
- -l session:cpus:5: Occupy at most 5 cpu cores at any one time.
- -l test:devices:2: Skip tests requiring more than 2 devices.
- -l session:devices:3: Occupy at most 3 devices at any one time.
- -l session:workers:8: Execute asynchronously using a pool of at most 8 workers
- -l batch:count:8: Execute tests in 8 batches.
- -l 'batch:time:30 min': Execute tests in batches having runtimes of approximately
    30 minutes.
""" % {
            "title": bold("Setting limits on resources"),
            "r_form": bold("[scope:]type:value"),
            "r_arg": bold("-l resource"),
            "r_scope": bold("scope"),
            "r_type": bold("type"),
            "r_value": bold("value"),
            "examples": bold("Examples"),
        }
        print(resource_help)
