import argparse
from typing import TYPE_CHECKING

from _nvtest.environment import Environment
from _nvtest.test.partition import dump_partitions
from _nvtest.test.partition import partition_n
from _nvtest.test.partition import partition_t
from _nvtest.util.time import time_in_seconds
from _nvtest.util.time import timestamp

from .common import Command
from .common import ConsolePrinter
from .common import add_mark_arguments

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session


class CreateBatches(Command, ConsolePrinter):
    name = "create-batches"
    description = "Create test batches, but don't run them"

    def __init__(self, config: "Config", session: "Session") -> None:
        self.config = config
        self.session = session
        self.option = argparse.Namespace(
            on_options=self.session.option.on_options,
            keyword_expr=self.session.option.keyword_expr,
            timeout=None,
            max_workers=1,
            copy_all_resources=None,
            runner=None,
            runner_options=None,
            batch_size=None,
        )

    @property
    def mode(self):
        return "write"

    def setup(self):
        self.print_section_header("Begin test case batching")
        self.print_front_matter()
        env = Environment(self.session.option.search_paths)
        self.print_text(
            "testpaths: {0}\n".format("\n           ".join(env.search_paths))
        )
        env.discover()
        self.cases = env.test_cases(
            self.session.config,
            on_options=self.session.option.on_options,
            keyword_expr=self.session.option.keyword_expr,
        )
        self.print_testcase_summary()

    def run(self) -> int:
        start = timestamp()
        cases_to_run = [case for case in self.cases if not case.skip]
        if self.session.option.batch_size_t is not None:
            self.print_text(
                f"Batching {len(cases_to_run)} test cases into "
                f"batches with runtime <= {self.session.option.batch_size_t} s."
            )
            batches = partition_t(cases_to_run, t=self.session.option.batch_size_t)
        else:
            self.print_text(
                f"Batching {len(cases_to_run)} test cases "
                f"into {self.session.option.batch_size_n} groups"
            )
            batches = partition_n(cases_to_run, n=self.session.option.batch_size_n)
        for batch in batches:
            self.print_text(
                f"Batch {batch.rank[0] + 1} has {len(batch)} tests "
                f"with an estimated cpu time of {batch.cputime:.2f}"
            )
        dest = self.session.workdir
        dump_partitions(batches, dest=dest)
        duration = timestamp() - start
        self.print_section_header(f"Finished test case batching ({duration:.2} s.)")
        return 0

    def finish(self):
        ...

    @staticmethod
    def add_options(parser: argparse.ArgumentParser):
        add_mark_arguments(parser)
        g = parser.add_mutually_exclusive_group()
        g.add_argument(
            "-n",
            type=int,
            dest="batch_size_n",
            default=8,
            help="Batch tests into n batches  [default: %(default)s]",
        )
        g.add_argument(
            "-t",
            type=time_in_seconds,
            dest="batch_size_t",
            default=None,
            help="Batch tests with batch runtime <= t s.[default: %(default)s]",
        )
        parser.add_argument("search_paths", nargs="+", help="Search paths")
