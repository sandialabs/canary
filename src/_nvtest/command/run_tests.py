import argparse
import json
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING

from _nvtest.environment import Environment
from _nvtest.error import StopExecution
from _nvtest.executor import Executor
from _nvtest.io.cdash import Reporter as CDashReporter
from _nvtest.io.cdash import TestData as CDashTestData
from _nvtest.mark.match import deselect_by_keyword
from _nvtest.session.argparsing import ArgumentParser
from _nvtest.test.enums import Result
from _nvtest.test.enums import Skip
from _nvtest.test.testcase import TestCase
from _nvtest.util import tty
from _nvtest.util.graph import TopologicalSorter
from _nvtest.util.misc import ns2dict
from _nvtest.util.returncode import compute_returncode
from _nvtest.util.time import time_in_seconds

from .common import Command
from .common import ConsolePrinter
from .common import add_cdash_arguments
from .common import add_mark_arguments
from .common import default_timeout

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


class RunTests(Command, ConsolePrinter):
    name = "run-tests"
    description = "Run the tests"
    executor: Executor
    cases: list[TestCase]

    def __init__(self, config: "Config", session: "Session") -> None:
        super().__init__(config, session)
        self._mode: str = "write"
        self.search_paths: list[str] = session.option.search_paths or []
        if len(self.search_paths) == 1 and session.is_workdir(self.search_paths[0]):
            self._mode = "append"
            if session.option.workdir is not None:
                raise ValueError("Do not set value of work-dir when rerunning tests")
            session.option.workdir = self.search_paths[0]
        self.option = argparse.Namespace(
            on_options=self.session.option.on_options,
            keyword_expr=self.session.option.keyword_expr,
            timeout=self.session.option.timeout,
            max_workers=self.session.option.max_workers,
            copy_all_resources=self.session.option.copy_all_resources,
            runner="direct",
            runner_options=None,
            batch_size=None,
        )
        self.start: float = -1
        self.finish: float = -1

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def log_level(self) -> int:
        return self.config.log_level

    @property
    def index_file(self) -> str:
        return os.path.join(self.session.dotdir, "index.json")

    def setup(self) -> None:
        from _nvtest.session import ExitCode

        self.print_section_header("Beginning test session")
        self.print_front_matter()
        self.print_text(f"work directory: {self.session.workdir}")
        if self.session.mode == self.session.Mode.WRITE:
            env = Environment(self.search_paths)
            text = "search paths: {0}".format("\n           ".join(env.search_paths))
            self.print_text(text)
            env.discover()
            self.cases = env.test_cases(
                self.config,
                on_options=self.option.on_options,
                keyword_expr=self.option.keyword_expr,
            )
        else:
            assert self.session.mode == self.session.Mode.APPEND
            text = f"loading test index from {self.session.workdir!r}"
            self.print_text(text)
            self.load_index()
            self.filter_testcases()
        if self.log_level >= tty.WARN:
            self.print_testcase_summary()
        cases_to_run = [case for case in self.cases if not case.skip]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        self.executor = Executor(
            self.session,
            cases_to_run,
            runner=self.option.runner,
            max_workers=self.option.max_workers,
            runner_options=self.option.runner_options,
            batch_size=self.option.batch_size,
        )
        if self.session.mode == self.session.Mode.WRITE:
            self.executor.setup(copy_all_resources=self.option.copy_all_resources)
            self.dump_index()

    def run(self) -> int:
        self.start = time.time()
        self.executor.run(timeout=self.option.timeout)
        self.finish = time.time()
        return compute_returncode(self.cases)

    def teardown(self):
        if hasattr(self, "executor"):
            self.executor.teardown()
        if self.session.option.cdash_options:
            self.dump_cdash()
        duration = self.finish - self.start
        self.print_test_results_summary(duration)

    @staticmethod
    def add_options(parser: ArgumentParser):
        add_mark_arguments(parser)
        add_cdash_arguments(parser)
        parser.add_argument(
            "--timeout",
            type=time_in_seconds,
            default=default_timeout,
            help="Set a timeout on test execution [default: 1 hr]",
        )
        parser.add_argument(
            "--concurrent-tests",
            dest="max_workers",
            type=int,
            default=-1,
            help="Number of concurrent tests to run.  "
            "-1 determines the concurrency automatically [default: %(default)s]",
        )
        parser.add_argument(
            "--copy-all-resources",
            action="store_true",
            help="Do not link resources to the test "
            "directory, only copy [default: %(default)s]",
        )
        parser.add_argument("search_paths", nargs="+", help="Search paths")

    def dump_index(self):
        db = {}
        db["date"] = datetime.now().strftime("%c")
        db["option"] = ns2dict(self.option)
        db["search_paths"] = [os.path.abspath(p) for p in self.search_paths]
        cases = db.setdefault("cases", [])
        for case in self.cases:
            deps = [d.id for d in case.dependencies]
            kwds = {
                "name": str(case),
                "id": case.id,
                "dependencies": deps,
                "skip": case.skip.reason or None,
            }
            cases.append(kwds)
        db["batches"] = None
        if self.option.batch_size is not None:
            mapping = dict([(case.fullname, i) for (i, case) in enumerate(self.cases)])
            batches = []
            for batch in self.executor.work_items:
                case_ids = []
                for case in batch:
                    case_ids.append(mapping[case.fullname])
                batches.append(case_ids)
            db["batches"] = batches

        with open(self.index_file, "w") as fh:
            json.dump({"database": db}, fh, indent=2)

    def load_index(self) -> None:
        if not os.path.isfile(self.index_file):
            raise ValueError(f"Test index {self.index_file!r} not found")

        def find(container, arg):
            for item in container:
                if item == arg:
                    return item
            raise ValueError(f"Could not find {arg}")

        db = json.load(open(self.index_file))["database"]
        self.search_paths = db["search_paths"]

        ts: TopologicalSorter = TopologicalSorter()
        for case in db["cases"]:
            if not case["skip"]:
                ts.add(case["id"], *case["dependencies"])

        self.cases: list[TestCase] = []
        cache_dir = Executor._cache_dir
        for id in ts.static_order():
            path = os.path.join(self.session.workdir, cache_dir, id)
            case = TestCase.load(path)
            for (i, dep) in enumerate(case.dependencies):
                # dependencies already exist in ``cases`` because we are looping in
                # topological order
                case.dependencies[i] = find(self.cases, dep.id)
            self.cases.append(case)

        if self.option.timeout == default_timeout:
            self.option.timeout = db["options"]["timeout"]

        if db["options"]["batchsize"] is not None:
            self.option.batchsize = db["options"]["batchsize"]
            self.option.runner = db["options"]["runner"]
            if not self.option.runner_options:
                self.option.runner_options = db["options"]["runner_options"]

    def filter_testcases(self) -> None:
        for case in self.cases:
            if case.result not in (Result.NOTDONE, Result.NOTRUN, Result.SETUP):
                skip_reason = f"previous test result: {case.result.cname}"
                case.skip = Skip(skip_reason)
                if self.option.keyword_expr:
                    kwds = {kw for kw in case.keywords}
                    kwds.add(case.result.name.lower())
                    kwds.add(case.name)
                    kwds.update(case.parameters.keys())
                    kw_skip = deselect_by_keyword(kwds, self.option.keyword_expr)
                    if not kw_skip:
                        case.skip = Skip()
                        case.result = Result("notrun")

    def dump_cdash(self):
        kwds = self.session.option.cdash_options
        cases_to_run = [case for case in self.cases if not case.skip]
        data = CDashTestData(self.session, cases_to_run)
        reporter = CDashReporter(
            test_data=data,
            buildname=kwds.get("build", "BUILD"),
            baseurl=kwds.get("url"),
            project=kwds.get("project"),
            buildgroup=kwds.get("track"),
            site=kwds.get("site"),
        )
        dest = os.path.join(self.session.workdir, "cdash")
        reporter.create_cdash_reports(dest=dest)
