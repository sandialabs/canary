import io
import multiprocessing
import os
import threading
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from ... import config
from ...process_pool import ProcessPool
from ...queue import ResourceQueue
from ...resource_pool import make_resource_pool
from ...util import logging
from ...util.misc import digits
from ..hookspec import hookimpl
from ..types import Result

if TYPE_CHECKING:
    from ...resource_pool import ResourcePool
    from ...testcase import TestCase

global_lock = threading.Lock()
logger = logging.get_logger(__name__)


class TestCaseExecutor:
    """Defines plugin implementations for executing test cases"""

    def __init__(self):
        self._rpool: "ResourcePool | None" = None

    def get_rpool(self) -> "ResourcePool":
        # Use a function instead of @property since pluggy tries to inspect properties and causes
        # the resource pool to be instantiated prematurely
        if self._rpool is None:
            self._rpool = make_resource_pool(config._config)
        assert self._rpool is not None
        return self._rpool

    @hookimpl(trylast=True)
    def canary_resource_pool_accommodates(self, case: "TestCase") -> Result:
        rpool = self.get_rpool()
        return rpool.accommodates(case.required_resources())

    @hookimpl(trylast=True)
    def canary_resource_pool_count(self, type: "str") -> int:
        rpool = self.get_rpool()
        return rpool.count(type)

    @hookimpl(trylast=True)
    def canary_resource_pool_types(self) -> list[str]:
        rpool = self.get_rpool()
        return rpool.types

    @hookimpl(trylast=True)
    def canary_resource_pool_describe(self) -> str:
        rpool = self.get_rpool()
        fp = io.StringIO()
        rpool.dump(fp)
        return fp.getvalue()

    @hookimpl(trylast=True)
    def canary_runtests(self, cases: Sequence["TestCase"]) -> int:
        """Run each test case in ``cases``.

        Args:
        cases: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        rpool = self.get_rpool()
        queue = ResourceQueue.factory(global_lock, cases, resource_pool=rpool)
        runner = Runner()
        pool = ProcessPool(queue, runner)
        return pool.run()


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(
        self, case: "TestCase", queue: multiprocessing.Queue, *args: str, **kwargs: Any
    ) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        config.ensure_loaded()
        try:
            qsize = kwargs.get("qsize", 1)
            qrank = kwargs.get("qrank", 0)
            if summary := job_start_summary(case, qrank=qrank, qsize=qsize):
                logger.log(logging.EMIT, summary, extra={"prefix": ""})
            config.pluginmanager.hook.canary_testcase_setup(case=case)
            config.pluginmanager.hook.canary_testcase_run(
                case=case, queue=queue, qsize=qsize, qrank=qrank
            )
        finally:
            config.pluginmanager.hook.canary_testcase_finish(case=case)
            if summary := job_finish_summary(case, qrank=qrank, qsize=qsize):
                logger.log(logging.EMIT, summary, extra={"prefix": ""})


def job_start_summary(case: "TestCase", *, qrank: int | None, qsize: int | None) -> str:
    if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    if qrank is not None and qsize is not None:
        fmt.write("@*{[%s]} " % f"{qrank + 1:0{digits(qsize)}}/{qsize}")
    fmt.write("Starting test case @*b{%s}: %s" % (case.id[:7], case.display_name))
    return fmt.getvalue().strip()


def job_finish_summary(case: "TestCase", *, qrank: int | None, qsize: int | None) -> str:
    if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    if qrank is not None and qsize is not None:
        fmt.write("@*{[%s]} " % f"{qrank + 1:0{digits(qsize)}}/{qsize}")
    fmt.write(
        "Finished test case @*b{%s}: %s @*%s{%s}"
        % (case.id[:7], case.display_name, case.status.color[0], case.status.name)
    )
    return fmt.getvalue().strip()
