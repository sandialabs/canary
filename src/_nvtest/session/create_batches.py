from typing import Optional

from ..environment import Environment
from ..session.argparsing import Parser
from ..test.partition import dump_partitions
from ..test.partition import partition_n
from ..test.partition import partition_t
from ..util.time import time_in_seconds
from ..util.time import timestamp
from .base import Session
from .common import add_mark_arguments
from .common import add_workdir_arguments


class CreateBatches(Session):
    """Create test batches, but don't run them"""

    family = "batch"

    def __init__(
        self, *, invocation_params: Optional[Session.InvocationParams] = None
    ) -> None:
        super().__init__(invocation_params=invocation_params)
        self.workdir = self.option.workdir or "./Batches"

    @property
    def mode(self):
        return self.Mode.WRITE

    def setup(self):
        self.print_section_header("Begin test case batching")
        self.print_front_matter()
        env = Environment(self.option.search_paths)
        self.print_text(
            "testpaths: {0}\n".format("\n           ".join(env.search_paths))
        )
        env.discover()
        self.cases = env.test_cases(
            self,
            on_options=self.option.on_options,
            keyword_expr=self.option.keyword_expr,
        )
        self.print_testcase_summary()

    def run(self) -> int:
        start = timestamp()
        cases_to_run = [case for case in self.cases if not case.skip]
        if self.option.batch_size_t is not None:
            self.print_text(
                f"Batching {len(cases_to_run)} test cases into "
                f"batches with runtime <= {self.option.batch_size_t} s."
            )
            batches = partition_t(cases_to_run, t=self.option.batch_size_t)
        else:
            self.print_text(
                f"Batching {len(cases_to_run)} test cases "
                f"into {self.option.batch_size_n} groups"
            )
            batches = partition_n(cases_to_run, n=self.option.batch_size_n)
        for batch in batches:
            self.print_text(
                f"Batch {batch.rank[0] + 1} has {len(batch)} tests "
                f"with an estimated cpu time of {batch.cputime:.2f}"
            )
        dest = self.workdir
        dump_partitions(batches, dest=dest)
        duration = timestamp() - start
        self.print_section_header(f"Finished test case batching ({duration:.2} s.)")
        return 0

    def teardown(self):
        ...

    @staticmethod
    def setup_parser(parser: Parser):
        add_workdir_arguments(parser)
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
