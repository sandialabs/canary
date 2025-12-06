# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import heapq
import io
import time

import canary
from _canary import queue
from _canary.protocols import JobProtocol
from _canary.third_party import color
from _canary.util.time import hhmmss

logger = canary.get_logger(__name__)


class ResourceQueue(queue.ResourceQueue):
    def put(self, *jobs: JobProtocol) -> None:
        for job in jobs:
            if job.status.category not in ("READY", "PENDING"):
                raise ValueError(f"Job {job} must be READY or PENDING, got {job.status.category}")
        with self.lock:
            for batch in jobs:
                slot = queue.HeapSlot(job=batch)  # ty: ignore[invalid-argument-type]
                heapq.heappush(self._heap, slot)
                logger.debug(f"Job {batch.id} added to queue with cost {-slot.cost}")
                self._dependents.update({case.id: case.dependencies for case in batch})

    def update_pending(self, finished_job: JobProtocol) -> None:
        dependents = [dep for case in finished_job for dep in self._dependents.get(case.id, [])]
        if not dependents:
            return
        completed = {case.id: case for case in finished_job}
        for job in dependents:
            for i, dep in enumerate(job.dependencies):
                if dep.id in completed:
                    job.dependencies[i] = completed[dep.id]

    def cases(self) -> list[JobProtocol]:
        cases: list[JobProtocol] = [case for batch in self._heap for case in batch]  # type: ignore
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

    def status(self, start: float | None = None) -> str:
        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done = sum([len(_) for _ in self._finished.values()])
            busy = sum([len(_) for _ in self._busy.values()])
            pending = sum([len(_.job) for _ in self._heap])  # type: ignore
            total = done + busy + pending
            for batch in self._finished.values():
                for case in batch:
                    if case.status.category in ("SUCCESS", "XDIFF", "XFAIL"):
                        p += 1
                    elif case.status.category == "DIFFED":
                        d += 1
                    elif case.status.category == "TIMEOUT":
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
