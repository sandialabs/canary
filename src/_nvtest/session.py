import io
import json
import os
import pickle
import random
import signal
import threading
import time
import traceback
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from functools import partial
from itertools import repeat
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from . import config
from . import plugin
from .database import Database
from .error import FailFast
from .error import StopExecution
from .finder import Finder
from .queues import BatchResourceQueue
from .queues import DirectResourceQueue
from .queues import Empty as EmptyQueue
from .queues import ResourceQueue
from .test.batch import Batch
from .test.case import TestCase
from .test.generator import TestGenerator
from .test.status import Status
from .third_party import color
from .util import glyphs
from .util import keyboard
from .util import logging
from .util import parallel
from .util.filesystem import force_remove
from .util.filesystem import mkdirp
from .util.filesystem import working_dir
from .util.graph import TopologicalSorter
from .util.misc import partition
from .util.resource import BatchInfo
from .util.resource import ResourceInfo
from .util.returncode import compute_returncode
from .util.time import hhmmss
from .when import when

default_timeout = 60 * 60  # 60 minutes
default_batchsize = 30 * 60  # 30 minutes
global_session_lock = threading.Lock()
batch_store_path = "B"


class ExitCode:
    OK: int = 0
    INTERNAL_ERROR: int = 1
    INTERRUPTED: int = 3
    TIMEOUT: int = 5
    NO_TESTS_COLLECTED: int = 7

    @staticmethod
    def compute(cases: list[TestCase]) -> int:
        return compute_returncode(cases)


class Session:
    tagfile = "SESSION.TAG"
    default_worktree = "./TestResults"
    data_file = "session.data.json"
    resource_file = "resources.data.json"

    def __init__(self, path: str, mode: str = "r", force: bool = False) -> None:
        if mode not in "arw":
            raise ValueError(f"invalid mode: {mode!r}")
        self.root: str
        if mode == "w":
            path = os.path.abspath(path)
            if force and os.path.exists(path):
                if not os.getenv("NVTEST_MAKE_DOCS"):
                    logging.warning(f"Removing {path}")
                force_remove(path)
            if os.path.exists(path):
                raise DirectoryExistsError(f"{path}: directory exists")
            self.root = path
        else:
            root = self.find_root(path)
            if root is None:
                raise NotASession("not a nvtest session (or any of the parent directories)")
            self.root = root
        self.mode = mode
        self.search_paths: dict[str, list[str]] = {}
        self.generators: list[TestGenerator] = list()
        self.cases: list[TestCase] = list()
        self.db = Database(self.config_dir)
        if mode in "ra":
            self.load()
        else:
            self.initialize()
        self.exitstatus = -1
        self.returncode = -1
        self.mode = mode

    @property
    def config_dir(self):
        return os.path.join(self.root, ".nvtest")

    @staticmethod
    def find_root(path: str):
        path = os.path.abspath(path)
        while True:
            if os.path.exists(os.path.join(path, Session.tagfile)):
                return os.path.dirname(path)
            elif os.path.exists(os.path.join(path, ".nvtest", Session.tagfile)):
                return path
            path = os.path.dirname(path)
            if path == os.path.sep:
                break
        return None

    def load(self) -> None:
        logging.debug(f"Loading test session in {self.root}")
        file = os.path.join(self.config_dir, self.data_file)
        with open(file, "rb") as fh:
            data = json.load(fh)
        for var, val in data.items():
            setattr(self, var, val)
        file = os.path.join(self.config_dir, "files.data.p")
        if os.path.exists(file):
            with open(file, "rb") as fh:
                self.generators = pickle.load(fh)
        self.cases = self.db.load()
        self.set_config_values()

    def initialize(self) -> None:
        logging.debug(f"Initializing test session in {self.root}")
        file = os.path.join(self.config_dir, self.tagfile)
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a results directory tag automatically created by nvtest.\n")
        self.set_config_values(write=True)
        self.save()

    def set_config_values(self, write: bool = False):
        config.set("session:root", self.root, scope="session")
        config.set("session:invocation_dir", config.invocation_dir, scope="session")
        config.set("session:start", config.invocation_dir, scope="session")
        for attr in ("sockets_per_node", "cores_per_socket", "cpu_count"):
            value = config.get(f"machine:{attr}", scope="local")
            if value is not None:
                config.set(f"machine:{attr}", value, scope="session")
        for section in ("build", "config", "machine", "option", "variables"):
            # transfer options to the session scope and save it for future sessions
            data = config.get(section, scope="local") or {}
            for key, value in data.items():
                config.set(f"{section}:{key}", value, scope="session")
        if write:
            file = os.path.join(self.config_dir, "config")
            with open(file, "w") as fh:
                config.dump(fh, scope="session")

    def save(self) -> None:
        data: dict[str, Any] = {}
        for var, value in vars(self).items():
            if var not in ("files", "cases", "db"):
                data[var] = value
        file = os.path.join(self.config_dir, self.data_file)
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)

    def add_search_paths(self, search_paths: Union[dict[str, list[str]], list[str]]) -> None:
        """Add ``path`` to this session's search paths"""
        if isinstance(search_paths, list):
            search_paths = {path: [] for path in search_paths}
        if self.generators:
            raise ValueError("session is already populated")
        errors = 0
        for root, paths in search_paths.items():
            if not os.path.isdir(root):
                errors += 1
                logging.warning(f"{root}: directory does not exist and will not be searched")
        if errors:
            logging.warning("one or more search paths does not exist")
        for root, paths in search_paths.items():
            root = os.path.abspath(root)
            self.search_paths[root] = paths
        self.save()

    def discover(self):
        finder = Finder()
        for root, paths in self.search_paths.items():
            finder.add(root, *paths, tolerant=True)
        for hook in plugin.plugins("session", "discovery"):
            hook(self)
        finder.prepare()
        self.generators = finder.discover()
        file = os.path.join(self.config_dir, "files.data.p")
        with open(file, "wb") as fh:
            pickle.dump(self.generators, fh)
        logging.debug(f"Discovered {len(self.generators)} test files")

    def freeze(
        self,
        resourceinfo: Optional[ResourceInfo] = None,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        owners: Optional[set[str]] = None,
    ) -> None:
        self.cases = Finder.freeze(
            self.generators,
            resourceinfo=resourceinfo,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
            on_options=on_options,
            owners=owners,
        )
        cases_to_run = [case for case in self.cases if not case.masked]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        self.db.makeindex(self.cases)
        logging.debug(f"Collected {len(self.cases)} test cases from {len(self.generators)} files")

    def populate(self, copy_all_resources: bool = False) -> None:
        """Populate the work tree with test case assets"""
        logging.debug("Populating test case directories")
        with self.rc_environ():
            with working_dir(self.root):
                self.setup_testcases(copy_all_resources=copy_all_resources)

    def setup_testcases(self, copy_all_resources: bool = False) -> None:
        logging.debug("Setting up test cases")
        cases = [case for case in self.cases if not case.masked]
        ts: TopologicalSorter = TopologicalSorter()
        for case in cases:
            ts.add(case, *case.dependencies)
        ts.prepare()
        errors = 0
        while ts.is_active():
            group = ts.get_ready()
            args = zip(group, repeat(self.root), repeat(copy_all_resources))
            parallel.starmap(setup_individual_case, list(args))
            for case in group:
                # Since setup is run in a multiprocessing pool, the internal
                # state is lost and needs to be updated
                case.refresh()
                assert case.status.value in ("skipped", "ready", "pending")
                if case.exec_root is None:
                    errors += 1
                    logging.error(f"{case}: exec_root not set after setup")
            ts.done(*group)
        self.db.update(cases)
        if errors:
            raise ValueError("Stopping due to previous errors")

    def filter(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        start: Optional[str] = None,
        resourceinfo: Optional[ResourceInfo] = None,
        case_specs: Optional[list[str]] = None,
    ) -> list[TestCase]:
        resourceinfo = resourceinfo or ResourceInfo()
        explicit_start_path = start is not None
        if start is None:
            start = self.root
        elif not os.path.isabs(start):
            start = os.path.join(self.root, start)
        start = os.path.normpath(start)
        # mask tests and then later enable based on additional conditions
        for case in self.cases:
            if case.masked:
                continue
            if not case.exec_dir.startswith(start):
                case.status.set("masked", "Unreachable from start directory")
                continue
            if case_specs is not None:
                if any(case.matches(_) for _ in case_specs):
                    case.status.set("ready")
                else:
                    case.status.set(
                        "masked", color.colorize("deselected by @*b{testspec expression}")
                    )
                continue
            elif explicit_start_path:
                case.status.set("ready")
                continue
            if resourceinfo["test:cpus"] and case.processors > resourceinfo["test:cpus"]:
                n = resourceinfo["test:cpus"]
                case.status.set("masked", f"test requires more than {n} cpus")
                continue
            if resourceinfo["test:devices"] and case.devices > resourceinfo["test:devices"]:
                n = resourceinfo["test:devices"]
                case.status.set("masked", f"test requires more than {n} devices")
                continue
            when_expr: dict[str, str] = {}
            if parameter_expr:
                when_expr.update({"parameters": parameter_expr})
            if keyword_expr:
                when_expr.update({"keywords": keyword_expr})
            if when_expr:
                match = when(
                    when_expr,
                    parameters=case.parameters,
                    keywords=case.keywords(implicit=True),
                )
                if match:
                    case.status.set("ready" if not case.dependencies else "pending")
                elif case.status != "ready":
                    s = f"deselected due to previous status: {case.status.cname}"
                    case.status.set("masked", s)
                else:
                    case.status.set("masked", color.colorize("deselected by @*b{when expression}"))

        cases = [case for case in self.cases if case.status.value in ("pending", "ready")]
        return cases

    def bfilter(self, batch_store: Optional[int], batch_no: Optional[int]) -> list[TestCase]:
        dir = os.path.join(self.config_dir, BatchResourceQueue.store)
        if batch_store is None:
            batch_store = len(os.listdir(dir))  # use latest
        file = os.path.join(self.config_dir, BatchResourceQueue.store, str(batch_store), "index")
        with open(file, "r") as fh:
            fd = json.load(fh)
        case_ids: list[str] = fd["index"][str(batch_no)]
        for case in self.cases:
            if case.id in case_ids:
                case.status.set("ready")
            elif not case.masked:
                case.status.set("masked", f"case is not in batch {batch_no}")
        return [case for case in self.cases if case.status == "ready"]

    def run(
        self,
        cases: list[TestCase],
        *,
        resourceinfo: Optional[ResourceInfo] = None,
        batchinfo: Optional[BatchInfo] = None,
        fail_fast: bool = False,
        output: str = "progress-bar",
    ) -> int:
        if not cases:
            raise ValueError("There are no cases to run in this session")
        resourceinfo = resourceinfo or ResourceInfo()
        batchinfo = batchinfo or BatchInfo()
        queue = self.setup_queue(cases, resourceinfo, batchinfo)
        with self.rc_environ():
            with working_dir(self.root):
                self.process_testcases(
                    queue=queue,
                    resourceinfo=resourceinfo,
                    fail_fast=fail_fast,
                    output=output,
                    batchinfo=batchinfo,
                )
                for hook in plugin.plugins("session", "finish"):
                    hook(self)
        return self.returncode

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env: dict[str, Optional[str]] = {}
        variables = dict(config.get("variables"))
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        level = logging.get_level()
        os.environ["NVTEST_LOG_LEVEL"] = logging.get_level_name(level)
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def process_testcases(
        self,
        *,
        queue: ResourceQueue,
        resourceinfo: ResourceInfo,
        fail_fast: bool,
        output: str = "progress-bar",
        batchinfo: Optional[BatchInfo] = None,
    ) -> None:
        verbose: bool = output == "verbose"
        futures: dict = {}
        auto_cleanup: bool = True
        self.start = time.monotonic()
        duration = lambda: time.monotonic() - self.start
        timeout = resourceinfo["session:timeout"] or -1
        try:
            with ProcessPoolExecutor(max_workers=queue.workers) as ppe:
                runner_args = []
                runner_kwargs = dict(verbose=verbose, timeoutx=resourceinfo["test:timeoutx"])
                if batchinfo:
                    runner_args.extend(batchinfo.args)
                    if batchinfo.workers:
                        runner_kwargs["workers"] = batchinfo.workers
                while True:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        logging.emit(queue.status())
                    if not verbose:
                        queue.display_progress(self.start)
                    if timeout >= 0.0 and duration() > timeout:
                        raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                    try:
                        iid_obj = queue.get()
                        if iid_obj is None:
                            time.sleep(0.01)
                            continue
                        iid, obj = iid_obj
                    except EmptyQueue:
                        break
                    future = ppe.submit(obj, *runner_args, **runner_kwargs)
                    callback = partial(self.done_callback, iid, queue, fail_fast)
                    future.add_done_callback(callback)
                    futures[iid] = (obj, future)
        except BaseException as e:
            if ppe._processes:
                for proc in ppe._processes:
                    os.kill(proc, signal.SIGINT)
            ppe.shutdown(wait=True)
            if isinstance(e, KeyboardInterrupt):
                self.returncode = signal.SIGINT.value
                auto_cleanup = False
            elif isinstance(e, FailFast):
                name, code = e.args
                self.returncode = code
                auto_cleanup = False
                raise StopExecution(f"fail_fast: {name}", code)
            else:
                logging.error(traceback.format_exc())
                self.returncode = compute_returncode(queue.cases())
                raise
        else:
            if not verbose:
                queue.display_progress(self.start, last=True)
            self.returncode = compute_returncode(queue.cases())
        finally:
            self.finish = time.monotonic()
            if auto_cleanup:
                for case in queue.cases():
                    if case.status == "ready":
                        case.status.set("failed", "Case failed to start")
                        case.save()
                    elif case.status == "running":
                        case.status.set("failed", "Case failed to stop")
                        case.save()

    def done_callback(
        self, iid: int, queue: ResourceQueue, fail_fast: bool, future: Future
    ) -> None:
        if future.cancelled():
            return
        try:
            future.result()
        except BrokenProcessPool:
            # The future was probably killed by fail_fast or a keyboard interrupt
            return

        # The case (or batch) was run in a subprocess.  The object must be
        # refreshed so that the state in this main thread is up to date.

        obj: Union[TestCase, Batch] = queue.done(iid)
        if not isinstance(obj, (Batch, TestCase)):
            logging.error(f"Expected TestCase or Batch, got {obj.__class__.__name__}")
            return

        obj.refresh()
        if isinstance(obj, TestCase):
            self.db.update([obj])
            if fail_fast and obj.status != "success":
                code = compute_returncode([obj])
                raise FailFast(str(obj), code)
        else:
            assert isinstance(obj, Batch)
            fd = self.db.read()
            for case in obj:
                if case.id not in fd:
                    logging.error(f"case ID {case.id} not in batch {obj.world_rank}")
                    continue
                if case.status.value != fd[case.id]["status"].value:
                    fs = case.status.value
                    ss = fd[case.id]["status"].value
                    logging.warning(
                        f"batch {obj.world_rank}, {case}: "
                        f"expected status of future.result to be {ss}, not {fs}"
                    )
            if fail_fast and any(_.status != "success" for _ in obj):
                code = compute_returncode(obj.cases)
                raise FailFast(str(obj), code)

    def setup_queue(
        self, cases: list[TestCase], resourceinfo: ResourceInfo, batchinfo: BatchInfo
    ) -> ResourceQueue:
        queue: ResourceQueue
        if batchinfo.scheduler is None:
            if batchinfo.count is not None or batchinfo.length is not None:
                raise ValueError("batched execution requires a scheduler")
            queue = DirectResourceQueue(resourceinfo, global_session_lock)
        else:
            if batchinfo.count is None and batchinfo.length is None:
                batchinfo.length = default_batchsize
            queue = BatchResourceQueue(resourceinfo, batchinfo, global_session_lock)
        for case in cases:
            if case.status.value not in ("ready", "pending"):
                raise ValueError(f"{case}: case is not ready or pending")
            elif case.exec_root is None:
                raise ValueError(f"{case}: exec root is not set")
        queue.put(*cases)
        queue.prepare()
        if queue.empty():
            raise ValueError("There are no cases to run in this session")
        return queue

    def blogfile(self, batch_no: int, batch_store: Optional[int]) -> str:
        dir = os.path.join(self.config_dir, BatchResourceQueue.store)
        if batch_store is None:
            batch_store = len(os.listdir(dir))  # use latest
        index = os.path.join(dir, str(batch_store), BatchResourceQueue.index_file)
        with open(index) as fh:
            fd = json.load(fh)
            n = len(fd["index"])
        f = os.path.join(dir, str(batch_store), f"out.{n}.{batch_no}.txt")
        return f

    @staticmethod
    def overview(cases: list[TestCase]) -> str:
        def unreachable(c):
            return c.status == "skipped" and c.status.details.startswith("Unreachable")

        string = io.StringIO()
        files = {case.file for case in cases}
        _, cases = partition(cases, lambda c: unreachable(c))
        fmt = "@*%s{%s} %d test%s from %d file%s\n"
        n, N = len(cases), len(files)
        s, S = "s" if n > 1 else "", "s" if N > 1 else ""
        string.write(color.colorize(fmt % ("c", "collected", n, s, N, S)))
        cases_to_run = [case for case in cases if not case.masked and not case.skipped]
        files = {case.file for case in cases_to_run}
        n, N = len(cases_to_run), len(files)
        s = "s " if n > 1 else " "
        S = "s " if N > 1 else ""
        string.write(color.colorize(fmt % ("g", "running", n, s, N, S)))
        skipped = [case for case in cases if case.masked]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.status.details
            assert isinstance(reason, str)
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        if skipped:
            string.write(color.colorize("@*b{skipping} %d test cases" % len(skipped)) + "\n")
            reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
            for reason in reversed(reasons):
                string.write(f"{glyphs.bullet} {skipped_reasons[reason]} {reason.lstrip()}\n")
        return string.getvalue()

    @staticmethod
    def summary(cases: list[TestCase], include_pass: bool = True) -> str:
        string = io.StringIO()
        if not cases:
            string.write("Nothing to report\n")
            return string.getvalue()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            totals.setdefault(case.status.value, []).append(case)
        string.write(color.colorize("@*{Short test summary info}\n"))
        for status in Status.members:
            if not include_pass and status == "success":
                continue
            glyph = Status.glyph(status)
            if status in totals:
                for case in sorted(totals[status], key=lambda t: t.name):
                    string.write("%s %s\n" % (glyph, cformat(case)))
        string.write("\n")
        return string.getvalue()

    @staticmethod
    def footer(cases: list[TestCase], duration: float = -1, title="Session done") -> str:
        string = io.StringIO()
        if duration == -1:
            finish = max(_.finish for _ in cases)
            start = min(_.start for _ in cases)
            duration = finish - start

        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        N = len(cases)
        summary = ["@*b{%d total}" % N]
        for member in Status.colors:
            n = len(totals.get(member, []))
            if n:
                c = Status.colors[member]
                stat = totals[member][0].status.name
                summary.append(color.colorize("@%s{%d %s}" % (c, n, stat.lower())))
        x, y = random.sample([glyphs.sparkles, glyphs.collision, glyphs.highvolt], 2)
        kwds = {"x": x, "y": y, "s": ", ".join(summary), "t": hhmmss(duration), "title": title}
        string.write(color.colorize("%(x)s%(x)s @*{%(title)s} -- %(s)s in @*{%(t)s}\n" % kwds))
        return string.getvalue()

    @staticmethod
    def durations(cases: list[TestCase], N: int) -> str:
        string = io.StringIO()
        cases = [c for c in cases if c.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        kwds = {"t": glyphs.turtle, "N": N}
        string.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
        for case in sorted_cases:
            string.write("  %6.2f     %s\n" % (case.duration, case.pretty_repr()))
        string.write("\n")
        return string.getvalue()

    @staticmethod
    def status(cases: list[TestCase], show_logs: bool = False, sortby: str = "duration") -> str:
        string = io.StringIO()
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            if case.masked:
                totals.setdefault("masked", []).append(case)
            else:
                totals.setdefault(case.status.value, []).append(case)
        nprinted = 0
        for member in Status.members:
            if member in totals:
                for case in sort_cases_by(totals[member], field=sortby):
                    glyph = Status.glyph(case.status.value)
                    string.write("%s %s\n" % (glyph, cformat(case, show_log=show_logs)))
                    nprinted += 1
        return string.getvalue()


def setup_individual_case(case, exec_root, copy_all_resources):
    logging.debug(f"Setting up {case}")
    case.setup(exec_root, copy_all_resources=copy_all_resources)


def cformat(case: TestCase, show_log: bool = False) -> str:
    id = color.colorize("@*b{%s}" % case.id[:7])
    if case.masked:
        string = "@*c{EXCLUDED} %s %s: %s" % (id, case.pretty_repr(), case.status.details)
        return color.colorize(string)
    string = "%s %s %s" % (case.status.cname, id, case.pretty_repr())
    if case.duration > 0:
        string += " (%.2fs.)" % case.duration
    elif case.status == "skipped":
        string += ": Skipped due to %s" % case.status.details
    if show_log:
        f = os.path.relpath(case.logfile(), os.getcwd())
        string += color.colorize(": @m{%s}" % f)
    return string


def sort_cases_by(cases: list[TestCase], field="duration") -> list[TestCase]:
    if cases and isinstance(getattr(cases[0], field), str):
        return sorted(cases, key=lambda case: getattr(case, field).lower())
    return sorted(cases, key=lambda case: getattr(case, field))


class DirectoryExistsError(Exception):
    pass


class NotASession(Exception):
    pass
