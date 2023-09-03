import os
import time
from typing import Optional

from ..environment import Environment
from ..error import StopExecution
from ..executor import Executor
from ..mark.match import deselect_by_keyword
from ..session.argparsing import ArgumentParser
from ..test.enums import Result
from ..test.enums import Skip
from ..util import tty
from ..util.returncode import compute_returncode
from ..util.time import time_in_seconds
from .base import Session
from .common import add_mark_arguments
from .common import default_timeout


class RunTests(Session):
    """Run the tests"""

    family = "test"

    executor: Executor

    def __init__(
        self, *, invocation_params: Optional[Session.InvocationParams] = None
    ) -> None:
        super().__init__(invocation_params=invocation_params)
        self._mode: self.Mode = self.Mode.WRITE
        self.search_paths: list[str] = self.option.search_paths or []
        if len(self.search_paths) == 1 and self.is_workdir(self.search_paths[0]):
            self._mode = self.Mode.APPEND
            if self.option.workdir is not None:
                raise ValueError("Do not set value of work-dir when rerunning tests")
            self.option.workdir = self.search_paths[0]
        self.option.runner = "direct"
        self.option.runner_options = None
        self.option.batch_size = None

    @property
    def mode(self) -> Session.Mode:
        return self._mode

    def setup(self) -> None:
        from _nvtest.session import ExitCode

        self.print_section_header("Beginning test session")
        self.print_front_matter()
        self.print_text(f"work directory: {self.workdir}")
        if self.mode == self.Mode.WRITE:
            env = Environment(self.search_paths)
            text = "search paths: {0}".format("\n           ".join(env.search_paths))
            self.print_text(text)
            env.discover()
            self.cases = env.test_cases(
                self,
                on_options=self.option.on_options,
                keyword_expr=self.option.keyword_expr,
            )
        else:
            assert self.mode == self.Mode.APPEND
            text = f"loading test index from {self.workdir!r}"
            self.print_text(text)
            self.load_index()
            self.filter_testcases()
        if self.log_level >= tty.WARN:
            self.print_testcase_summary()
        cases_to_run = [case for case in self.cases if not case.skip]
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        self.executor = Executor(
            self,
            cases_to_run,
            runner=self.option.runner,
            max_workers=self.option.max_workers,
            runner_options=self.option.runner_options,
            batch_size=self.option.batch_size,
        )
        if self.mode == self.Mode.WRITE:
            self.executor.setup(copy_all_resources=self.option.copy_all_resources)
            self.dump_index()

    def run(self) -> int:
        try:
            self.start = time.time()
            self.executor.run(timeout=self.option.timeout)
        finally:
            self.finish = time.time()
        return compute_returncode(self.cases)

    def teardown(self):
        if hasattr(self, "executor"):
            self.executor.teardown()
        duration = self.finish - self.start
        self.print_test_results_summary(duration)

    @staticmethod
    def setup_parser(parser: ArgumentParser):
        add_mark_arguments(parser)
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
        paths = [os.path.abspath(p) for p in self.search_paths]
        super().dump_index(search_paths=paths)

    def load_index(self) -> None:
        kwds = super().load_index()
        if not os.path.isfile(self.index_file):
            raise ValueError(f"{self.index_file!r} not found")
        if self.option.timeout == default_timeout:
            self.option.timeout = kwds["option"]["timeout"]
        if kwds["option"]["batch_size"] is not None:
            self.option.batch_size = kwds["option"]["batch_size"]
            self.option.runner = kwds["option"]["runner"]
            if not self.option.runner_options:
                self.option.runner_options = kwds["option"]["runner_options"]

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
