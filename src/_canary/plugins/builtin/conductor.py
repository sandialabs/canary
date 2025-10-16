import io
import os
import threading
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from ... import config
from ...queue import ResourceQueue
from ...queue import process_queue
from ...util import logging
from ...util.misc import digits
from ..hookspec import hookimpl
from ..types import Result

if TYPE_CHECKING:
    from ...testcase import TestCase

global_lock = threading.Lock()
logger = logging.get_logger(__name__)


class Conductor:
    @hookimpl(trylast=True)
    def canary_resources_avail(self, case: "TestCase") -> Result:
        return config.resource_pool.accommodates(case)

    @hookimpl(trylast=True)
    def canary_resource_count(self, type: "str") -> int:
        return config.resource_pool.count(type)

    @hookimpl(trylast=True)
    def canary_resource_types(self) -> list[str]:
        return config.resource_pool.types

    @hookimpl(trylast=True)
    def canary_runtests(self, cases: Sequence["TestCase"]) -> int:
        """Run each test case in ``cases``.

        Args:
        cases: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        queue = ResourceQueue.factory(global_lock, cases, resource_pool=config.resource_pool)
        runner = Runner()
        return process_queue(queue, runner)


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, case: "TestCase", *args: str, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        config.ensure_loaded()
        try:
            qsize = kwargs.get("qsize", 1)
            qrank = kwargs.get("qrank", 0)
            if summary := job_start_summary(case, qrank=qrank, qsize=qsize):
                logger.log(logging.EMIT, summary, extra={"prefix": ""})
            config.pluginmanager.hook.canary_testcase_setup(case=case)
            config.pluginmanager.hook.canary_testcase_run(case=case, qsize=qsize, qrank=qrank)
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
    fmt.write("Starting test case @*b{%id}: %X")
    return case.format(fmt.getvalue()).strip()


def job_finish_summary(case: "TestCase", *, qrank: int | None, qsize: int | None) -> str:
    if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    if qrank is not None and qsize is not None:
        fmt.write("@*{[%s]} " % f"{qrank + 1:0{digits(qsize)}}/{qsize}")
    fmt.write("Finished test case @*b{%id}: %X %s.n")
    return case.format(fmt.getvalue()).strip()
