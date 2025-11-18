import io
import multiprocessing
import threading
from typing import TYPE_CHECKING
from typing import Any

from ... import config
from ...queue import ResourceQueue
from ...queue_executor import ResourceQueueExecutor
from ...resource_pool import make_resource_pool
from ...util import logging
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
            self._rpool = make_resource_pool(config._config)  # ty: ignore[invalid-argument-type]
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
    def canary_runtests(self, cases: list["TestCase"]) -> int:
        """Run each test case in ``cases``.

        Args:
        jobs: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        try:
            rpool = self.get_rpool()
            queue = ResourceQueue(lock=global_lock, resource_pool=rpool, jobs=cases)  # ty: ignore[invalid-argument-type]
            queue.prepare()
        except Exception:
            logger.exception("Unable to create resource queue")
            raise
        runner = Runner()
        max_workers = config.getoption("workers") or -1
        with ResourceQueueExecutor(queue, runner, max_workers=max_workers) as ex:
            return ex.run()


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(
        self, case: "TestCase", queue: multiprocessing.Queue, *args: str, **kwargs: Any
    ) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        config.ensure_loaded()
        try:
            config.pluginmanager.hook.canary_testcase_setup(case=case)
            config.pluginmanager.hook.canary_testcase_run(case=case, queue=queue)
        finally:
            config.pluginmanager.hook.canary_testcase_finish(case=case)
