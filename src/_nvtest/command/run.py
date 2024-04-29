import argparse
import json
import os
import time
import traceback
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
from ..session import ExitCode
from ..session import Session
from ..session import default_batchsize
from ..test.case import TestCase
from ..third_party.color import colorize
from ..util import logging
from ..util.banner import banner
from ..util.filesystem import force_remove
from .common import add_mark_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments
from .common import setdefault

valid_schedulers = (None, "shell", "slurm")

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Run the tests"


def setup_parser(parser: "Parser"):
    parser.epilog = pathspec_epilog()
    add_work_tree_arguments(parser)
    add_mark_arguments(parser)
    group = parser.add_argument_group("console reporting")
    group.add_argument(
        "-v",
        action="store_true",
        default=False,
        help="Print each test case as it starts/finished, "
        "otherwise print a progress bar [default: %(default)s]",
    )
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
        help="Do not link resources to the test directory, only copy [default: %(default)s]",
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
    u_help_msg = colorize(
        "Pass @*{option} as an option to the test script. "
        "If @*{option} contains commas, it is split into multiple options at the "
        "commas. You can use this syntax to pass an argument to the script. "
        "For example, -U,-A,XXXX passes -A XXXX to the script."
    )
    parser.add_argument(
        "-U",
        action=SchedulerOptions,
        dest="script_options",
        metavar="option",
        help=u_help_msg,
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
        assert isinstance(option, str)
        options: list[str] = getattr(namespace, self.dest, None) or []
        options.extend(self.split_on_comma(option))
        setattr(namespace, self.dest, options)

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
    parse_pathspec(args)
    initstate: int = 0

    timer = Timer()
    logging.emit(banner() + "\n")
    with timer.timeit("setup"):
        session = setup_session(args)

    initstate = 1
    try:
        if args.until == "setup":
            logging.info("Stopping after setup (--until='setup')")
            return 0
        logging.info(colorize("@*{Beginning test session}"))
        initstate = 2
        with timer.timeit("run"):
            opts: list[str] = args.script_options or []
            session.exitstatus = session.run(
                *opts, timeout=args.session_timeout, fail_fast=args.fail_fast, verbose=args.v
            )
        if not args.no_summary:
            session.print_summary()
        if args.durations:
            session.print_durations(args.durations)
        run_duration = timer.duration("run")
        session.print_footer(duration=run_duration)
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
            raise ValueError(f"{path}: no such file or directory")


def _parse_in_session_pathspec(args: argparse.Namespace) -> None:
    assert config.get("session") is not None
    args.mode = "a"
    if args.work_tree is not None:
        raise ValueError(f"work_tree={args.work_tree} incompatible with path arguments")
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
            if finder.is_test_file(path):
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
                if finder.is_test_file(f):
                    name = os.path.splitext(os.path.basename(f))[0]
                    kwds.append(name)
            args.keyword_expr = " and ".join(kwds)
    return


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
    logging.info(colorize("@*{Setting up test session}"))
    p = config.get("system:os:name")
    v = config.get("python:version")
    logging.debug(f"Platform: {p} -- Python {v}")
    if args.wipe:
        if args.mode != "w":
            raise ValueError(f"Cannot wipe work directory with mode={args.mode}")
        work_tree = args.work_tree or Session.default_work_tree
        if os.path.exists(work_tree):
            logging.warning(f"Removing work tree {work_tree}")
            force_remove(work_tree)
    session: Session
    if args.mode == "w":
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
            test_timelimit=args.test_maxtime,
            timeout_multiplier=args.test_timeoutx or 1.0,
        )
        if not args.no_header:
            session.print_overview()
        session.setup(
            copy_all_resources=args.copy_all_resources,
            workers_per_batch=args.workers_per_batch,
            batch_count=args.batch_count,
            batch_time=args.batch_time,
            scheduler=args.scheduler,
            scheduler_options=args.scheduler_options,
        )
    else:
        logging.info(f"Loading test session in {config.get('session:work_tree')}")
        assert args.mode in "ba"
        session = Session.load(mode="a")
        scheduler = None
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
            session.filter(
                keyword_expr=args.keyword_expr,
                start=args.start,
                parameter_expr=args.parameter_expr,
                avail_cpus_per_test=args.cpus_per_test,
                avail_devices_per_test=args.devices_per_test,
                case_specs=getattr(args, "case_specs", None),
            )
            if session.ini_options.get("scheduler"):
                scheduler = session.ini_options["scheduler"]
                if args.scheduler and scheduler != args.scheduler:
                    raise ValueError("rerun scheduler is not the same as the original scheduler")
                scheduler_options = session.ini_options["scheduler_options"]
                args.scheduler_options = args.scheduler_options or scheduler_options
        session.setup_queue(scheduler=scheduler, scheduler_options=args.scheduler_options)
    session.exitstatus = ExitCode.OK
    return session


def bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)


def pathspec_epilog() -> str:
    pathspec_help = """\
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
        "run": bold("nvtest run"),
        "new": bold("new"),
        "existing": bold("existing"),
        "pathspec": bold("pathspec"),
        "id": bold("/ID"),
        "batch_no": bold("^[BATCH_ID]:BATCH_NO"),
        "paths": bold("paths"),
        "root": bold("root"),
    }
    return pathspec_help
