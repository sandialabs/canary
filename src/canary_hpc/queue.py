# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import heapq
import io
import threading
import time
from typing import TYPE_CHECKING
from typing import Any

import canary
from _canary import queue
from _canary.protocols import JobProtocol
from _canary.third_party import color
from _canary.util.time import hhmmss

from .batching import TestBatch
from .batching import batch_testcases

if TYPE_CHECKING:
    from _canary.resource_pool import ResourcePool


logger = canary.get_logger(__name__)


class ResourceQueue(queue.ResourceQueue):
    def __init__(
        self,
        lock: threading.Lock,
        resource_pool: "ResourcePool",
        jobs: list[JobProtocol] | None = None,
    ) -> None:
        super().__init__(lock=lock, resource_pool=resource_pool)
        self.tmp_buffer: list[JobProtocol] = []
        if jobs:
            for job in jobs:
                self.put(job)

    def put(self, *jobs: JobProtocol) -> None:
        for job in jobs:
            if canary.config.get("debug"):
                # The job should have already been validated
                check = self.rpool.accommodates(job)
                if not check:
                    raise ValueError(f"Cannot put inadmissible case in queue ({check.reason})")
            if job.status.name not in ("READY", "PENDING"):
                raise ValueError(f"Job {job} must be READY or PENDING, got {job.status.name}")
            else:
                self.tmp_buffer.append(job)

    def prepare(self, **kwds: Any) -> None:
        logger.debug("Preparing batch queue")
        batchspec = canary.config.getoption("canary_hpc_batchspec")
        if not batchspec:
            raise ValueError("Cannot partition test cases: missing batching options")
        batches: list[TestBatch] = batch_testcases(
            cases=self.tmp_buffer,
            layout=batchspec["layout"],
            count=batchspec["count"],
            duration=batchspec["duration"],
            nodes=batchspec["nodes"],
            cpus_per_node=kwds.get("cpus_per_node"),
        )
        if not batches:
            raise ValueError(
                "No test batches generated (this should never happen, "
                "the default batching scheme should have been used)"
            )
        fmt = "@*{Generated} %d batches from %d test cases"
        logger.info(fmt % (len(batches), len(self.tmp_buffer)))
        for batch in batches:
            slot = queue.HeapSlot(job=batch)  # ty: ignore[invalid-argument-type]
            heapq.heappush(self._heap, slot)
            logger.debug(f"Job {batch.id} added to queue with cost {-slot.cost}")

    def update_pending(self, job: JobProtocol) -> None:
        completed = {case.id: case for case in job}
        for slot in self._heap:
            job = slot.job
            for case in job:
                for i, dep in enumerate(case.dependencies):
                    if dep.id in completed:
                        case.dependencies[i] = completed[dep.id]

    def cases(self) -> list[JobProtocol]:
        cases: list[JobProtocol] = [case for batch in self._heep for case in batch]
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

    def status(self, start: float | None = None) -> str:
        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done = sum([len(_) for _ in self._finished.values()])
            busy = sum([len(_) for _ in self._busy.values()])
            pending = sum([len(_) for _ in self._heap])
            total = done + busy + pending
            for batch in self.finished():
                for case in batch:
                    if case.status.name in ("SUCCESS", "XDIFF", "XFAIL"):
                        p += 1
                    elif case.status.name == "DIFFED":
                        d += 1
                    elif case.status.name == "TIMEOUT":
                        t += 1
                    else:
                        f += 1
            fmt = "%d/%d running, %d/%d done, %d/%d queued "
            if start is not None:
                duration = hhmmss(time.time() - start)
                fmt += f"in {duration} "
            fmt += "(@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout})"
            text = color.colorize(fmt % (busy, total, done, total, pending, total, p, d, f, t))
            n = color.clen(text)
            header = color.colorize("@*c{%s}" % " status ".center(n + 10, "="))
            footer = color.colorize("@*c{%s}" % "=" * (n + 10))
            pad = color.colorize("@*c{====}")
            string.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        return string.getvalue()
