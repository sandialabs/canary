# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import threading
import time
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from . import config
from .hookspec import hookimpl
from .queue import ResourceQueue
from .resource_pool import make_resource_pool
from .resource_pool.rpool import Outcome
from .testcase import TestCase
from .util import logging
from .util.multiprocessing import SimpleQueue

if TYPE_CHECKING:
    from .queue_executor import EventTypes
    from .resource_pool import ResourcePool
    from .runtest import Runner

global_lock = threading.Lock()
logger = logging.get_logger(__name__)


class CanaryConductor:
    """Defines plugin implementations for executing test cases"""

    def __init__(self) -> None:
        self._rpool: "ResourcePool | None" = None

    def get_rpool(self) -> "ResourcePool":
        # Use a function instead of @property since pluggy tries to inspect properties and causes
        # the resource pool to be instantiated prematurely
        if self._rpool is None:
            assert config._config is not None
            self._rpool = make_resource_pool(config._config)
        assert self._rpool is not None
        return self._rpool

    @hookimpl(trylast=True)
    def canary_resource_pool_accommodates(self, case: "TestCase") -> Outcome:
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
    def canary_runtests(self, runner: "Runner") -> bool:
        """Run each test case in ``cases``.

        Args:
        jobs: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        from _canary.queue_executor import ResourceQueueExecutor

        try:
            rpool = self.get_rpool()
            queue = ResourceQueue(lock=global_lock, resource_pool=rpool)
            queue.put(*runner.cases)  # type: ignore
            queue.prepare()
        except Exception:
            logger.exception("Unable to create resource queue")
            raise
        executor = TestCaseExecutor()
        max_workers = config.getoption("workers") or -1
        with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
            # removing add_listener for now since it results in corrupted db from too many
            # concurrent writes
            # ex.add_listener(partial(self.put_result, runner))  # type: ignore
            ex.run()
        return True

    def put_result(self, runner: "Runner", event: "EventTypes", *args: Any) -> None:
        if event == "job_finished":
            case: TestCase = cast(TestCase, args[0].job)
            runner.workspace.db.put_result(case)


class TestCaseExecutor:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, case: "TestCase", queue: SimpleQueue, **kwargs: Any) -> None:
        try:
            now = time.time()
            queue.put(("SUBMITTED", now))
            case.timekeeper.submitted = now
            config.pluginmanager.hook.canary_runteststart(case=case)
            queue.put(("STARTED", time.time()))
            config.pluginmanager.hook.canary_runtest(case=case)
        finally:
            config.pluginmanager.hook.canary_runtest_finish(case=case)
