# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import threading
import time
from typing import TYPE_CHECKING
from typing import Any

from . import config
from .hookspec import hookimpl
from .job import Job
from .queue import ResourceQueue
from .resource_pool.rpool import Outcome
from .util import logging
from .util.multiprocessing import SimpleQueue

if TYPE_CHECKING:
    from .resource_pool import ResourcePool
    from .runtest import Runner

global_lock = threading.Lock()
logger = logging.get_logger(__name__)


class CanaryConductor:
    """Defines plugin implementations for executing job"""

    def get_rpool(self) -> "ResourcePool":
        # Use a function instead of @property since pluggy tries to inspect properties and causes
        # the resource pool to be instantiated prematurely
        assert config._config is not None
        return config.resource_manager.get_pool()

    @hookimpl(trylast=True)
    def canary_resource_pool_accommodates(self, case: "Job") -> Outcome:
        rpool = self.get_rpool()
        return rpool.accommodates(case.required_resources())

    @hookimpl(trylast=True)
    def canary_resource_pool_count(self, type: "str") -> int:
        rpool = self.get_rpool()
        return rpool.count(type)

    @hookimpl(trylast=True)
    def canary_resource_pool_count_per_node(self, type: "str") -> int:
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
        """Run each test jobs in ``jobs``.

        Args:
          jobs: test jobs to run

        Returns:
          The session returncode (0 for success)

        """
        from .queue_executor import ResourceQueueExecutor

        try:
            rpool = self.get_rpool()
            queue = ResourceQueue(lock=global_lock, resource_pool=rpool)
            queue.put(*runner.jobs)  # type: ignore
            queue.prepare()
        except Exception:
            logger.exception("Unable to create resource queue")
            raise
        executor = JobExecutor()
        max_workers = config.getoption("workers") or -1
        with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
            ex.add_listener(runner.workspace.testcase_done_callback)
            ex.run()
        return True


class JobExecutor:
    """Class for running ``AbstractJob``."""

    def __call__(self, job: "Job", queue: SimpleQueue, **kwargs: Any) -> None:
        from .status import Status

        def record_event(event: str, t: float) -> None:
            queue.put({"event": f"job_{event}", "timestamp": t})
            setattr(job.timekeeper, event, t)

        def mark_broken(phase: str, e: Exception) -> None:
            r = f"{e.__class__.__name__}({', '.join(repr(_) for _ in e.args)})"
            job.status = Status.BROKEN(reason=r)
            logger.debug(f"Failed to {phase} {job}", exc_info=e)
            job.save()

        record_event("submitted", time.time())
        try:
            config.pluginmanager.hook.canary_runteststart(case=job)
        except Exception as e:
            mark_broken("setup", e)
            return

        record_event("started", time.time())
        try:
            config.pluginmanager.hook.canary_runtest(case=job)
            job.timekeeper.finished = time.time()
        except Exception as e:
            mark_broken("run", e)
            return

        try:
            config.pluginmanager.hook.canary_runtest_finish(case=job)
        except Exception as e:
            logger.debug(f"Failed to teardown {job}", exc_info=e)
            return
