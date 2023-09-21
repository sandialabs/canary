import argparse
import os
import time
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

import toml

from ..error import StopExecution
from ..executor import Executor
from ..finder import Finder
from ..mark.match import deselect_by_keyword
from ..runner import valid_runners
from ..schemas import testpaths_schema
from ..test.enums import Result
from ..test.enums import Skip
from ..test.partition import Partition
from ..test.partition import load_partition
from ..test.testcase import TestCase
from ..util import tty
from ..util.misc import dedup
from ..util.returncode import compute_returncode
from ..util.time import time_in_seconds
from ..util.tty.color import colorize
from .base import Session
from .common import add_mark_arguments
from .common import add_timing_arguments
from .common import add_workdir_arguments

if TYPE_CHECKING:
    from ..config import Config
    from ..config.argparsing import Parser

default_workdir = "./TestResults"
default_batchsize = 30 * 60  # 30 minutes


class Run(Session):
    """Run the tests"""

    family = "test"
    executor: Executor
    finder: Finder
    batch: Partition

    def __init__(self, *, config: "Config") -> None:
        super().__init__(config=config)
        self._check_input_and_set_defaults()

    @property
    def mode(self) -> Session.Mode:
        return self._mode

    def _check_input_and_set_defaults(self) -> None:
        """Determines the execution mode and sets defaults.  One of APPEND or WRITE

        The heuristic is as follows:

        - If only one search path is given and it is a workdir, we are in append
          mode
        - Otherwise, write mode

        Sets

        """
        args = self.config.option
        if isinstance(args.timeout, str):
            args.timeout = time_in_seconds(args.timeout)

        search_paths = dedup([os.path.abspath(_) for _ in args.search_paths or []])
        if not search_paths and not args.test_defn_file:
            search_paths = [self.config.dir]
        previous_workdirs = [_ for _ in search_paths if self.is_workdir(_, ascend=True)]

        reuse = len(previous_workdirs) > 0
        if reuse and len(previous_workdirs) > 1:
            raise TypeError(
                f"at most one path argument can point to a previous session's "
                f"execution directory, but {len(previous_workdirs)} did"
            )
        if reuse and args.test_defn_file is not None:
            raise TypeError(
                "toml test definition file and path argument that points to a previous "
                "session's execution directory are incompatible"
            )

        self.finder = Finder()
        workdir = args.workdir or default_workdir
        if reuse:
            assert len(previous_workdirs) == 1
            if self.option.workdir is not None:
                raise TypeError("workdir should not be set when rerunning tests")
            mode = self.Mode.APPEND
            workdir = self.find_workdir(previous_workdirs[0])
        elif self.is_batch_file(args.test_defn_file):
            if search_paths:
                raise TypeError("-f BATCH_FILE not compatible with SEARCH_PATHS")
            try:
                workdir = self.find_workdir(os.path.dirname(args.test_defn_file))
                mode = self.Mode.APPEND
            except ValueError:
                mode = self.Mode.WRITE
        else:
            mode = self.Mode.WRITE
            for path in search_paths:
                self.finder.add(path)
            if args.test_defn_file:
                with open(args.test_defn_file, "r") as fh:
                    data = toml.load(fh)
                testpaths_schema.validate(data)
                testpaths = data["testpaths"]
                if isinstance(testpaths, list):
                    for path in testpaths:
                        self.finder.add(path)
                else:
                    for (root, paths) in testpaths.items():
                        self.finder.add(root, *paths)
            self.finder.prepare()
            workdir = os.path.normpath(workdir)

        if args.batch_size is None and args.batches is None:
            if args.runner not in (None, "direct"):
                args.batch_size = default_batchsize
            elif args.runner is None:
                args.runner = "direct"
        elif args.batch_size is not None or args.batches is not None:
            if args.runner in (None, "direct"):
                raise ValueError(
                    f"{args.runner} runner not compatible with batching options"
                )

        self._mode = mode
        self.workdir = workdir

    def setup(self) -> None:
        from _nvtest.session import ExitCode

        self.print_section_header("Beginning test session")
        self.print_front_matter()
        tag = ""
        if self.is_batch_file(self.option.test_defn_file):
            batch = load_partition(self.option.test_defn_file)
            self.print_text(f"batch {batch.rank[0] + 1} of {batch.rank[1]}")
            self.cases = [case for case in batch]
            if self.option.runner is None:
                self.option.runner = "direct"
            i, n = batch.rank
            self.dump(os.path.join(self.dotdir, f"session.json.{n}.{i}"))
            tag = f".{n}.{i}"
        elif self.mode == self.Mode.WRITE:
            self.finder.populate()
            self.cases = self.finder.test_cases(
                cpu_count=self.config.machine.cpu_count,
                on_options=self.option.on_options,
                keyword_expr=self.option.keyword_expr,
            )
        else:
            assert self.mode == self.Mode.APPEND
            text = f"loading test index from {self.workdir!r}"
            self.print_text(text)
            self.cases = self.load_index()
            self.filter_testcases()
        if self.log_level >= tty.WARN:
            self.print_testcase_summary()

        cases_to_run = self.cases_to_run()
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)

        self.executor = Executor(
            self,
            cases_to_run,
            max_workers=self.option.max_workers,
            runner=self.option.runner,
            runner_options=self.option.runner_options,
            batching_options=dict(
                batch_size=self.option.batch_size, num_batches=self.option.batches
            ),
            tag=tag,
        )
        if self.mode == self.Mode.WRITE:
            self.executor.setup(copy_all_resources=self.option.copy_all_resources)
            self.dump_index()

        if self.option.until == "setup":
            raise StopExecution("Setup complete", ExitCode.OK)

    def run(self) -> int:
        from _nvtest.session import ExitCode

        try:
            self.start = time.time()
            self.executor.run(
                timeout=self.option.timeout, fail_fast=self.option.fail_fast
            )
        finally:
            self.finish = time.time()
        if self.option.until == "run":
            raise StopExecution("Run complete", ExitCode.OK)
        return compute_returncode(self.cases)

    def teardown(self):
        if hasattr(self, "executor"):
            self.executor.teardown()
        super().teardown()
        duration = self.finish - self.start
        self.print_test_results_summary(duration)

    @staticmethod
    def setup_parser(parser: "Parser"):
        add_workdir_arguments(parser)
        add_mark_arguments(parser)
        add_timing_arguments(parser)
        parser.add_argument(
            "-u",
            "--until",
            choices=("setup", "run", "postrun"),
            help="Stage to stop after when testing [default: %(default)s]",
        )
        parser.add_argument(
            "-n",
            "--max-workers",
            type=int,
            default=None,
            help="Execute tests/batches asynchronously using a pool of at most "
            "MAX_WORKERS.  For batched runs, the default is 5.  For direct runs, the "
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
        parser.add_argument(
            "-f",
            dest="test_defn_file",
            metavar="TEST_DEFN_FILE",
            help="Read tests from file",
        )
        group = parser.add_argument_group(
            "Batching", description="Run tests in batches through a scheduler"
        )
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
            default=None,
            choices=valid_runners,
            help="Work load manager [default: %(default)s]",
        )
        help_msg = colorize(
            "Pass @*{option} as an option to the runner. "
            "If @*{option} contains commas, it is split into multiple options at the "
            "commas. You can use this syntax to pass an argument to the option. "
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
            "search_paths",
            metavar="file_or_dir",
            nargs="*",
            help="Test file[s] or directories to search",
        )

    def load_index(self) -> list[TestCase]:
        cases = super().load_index()
        #        if kwds["batch_size"] is not None:
        #            self.option.batch_size = kwds["batch_size"]
        #            self.option.runner = kwds["runner"]
        #            if not self.option.runner_options:
        #                self.option.runner_options = kwds["runner_options"]
        return cases

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


class UserInputError(Exception):
    ...
