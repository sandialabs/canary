# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import threading
import time
from typing import Any
from typing import Sequence

import canary
from _canary import queue
from _canary.third_party import color
from _canary.util.time import hhmmss

from .partitioning import partition_testcases
from .testbatch import TestBatch

logger = canary.get_logger(__name__)


class ResourceQueue(queue.AbstractResourceQueue):
    def __init__(self, *, lock: threading.Lock) -> None:
        workers = int(canary.config.getoption("workers", -1))
        super().__init__(lock=lock, workers=5 if workers < 0 else workers)
        self.tmp_buffer: list[canary.TestCase] = []

    @classmethod
    def factory(
        cls, lock: threading.Lock, cases: Sequence[canary.TestCase], **kwds: Any
    ) -> "ResourceQueue":
        self = ResourceQueue(lock=lock)
        self.put(*cases)
        self.prepare(**kwds)
        if self.empty():
            raise ValueError("There are no cases to run in this session")
        return self

    def iter_keys(self) -> list[int]:
        return list(self.buffer.keys())

    def prepare(self, **kwds: Any) -> None:
        logger.debug("Preparing batch queue")
        batchopts = canary.config.getoption("batchopts", {})
        if not batchopts:
            raise ValueError("Cannot partition test cases: missing batching options")
        batches: list[TestBatch] = partition_testcases(
            cases=self.tmp_buffer,
            batchspec=batchopts["spec"],
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
            self.buffer[len(self.buffer)] = batch

    def done(self, obj_no: int) -> TestBatch:  # type: ignore[override]
        with self.lock:
            if obj_no not in self._busy:
                raise RuntimeError(f"batch {obj_no} is not running")
            obj = self._finished[obj_no] = self._busy.pop(obj_no)
            canary.config.resource_pool.reclaim(obj.resources)
            obj.free_resources()
            completed = dict([(_.id, _) for _ in self.finished()])
            for batch in self.buffer.values():
                for case in batch:
                    for i, dep in enumerate(case.dependencies):
                        if dep.id in completed:
                            case.dependencies[i] = completed[dep.id]
            return self._finished[obj_no]

    def retry(self, obj_no: int) -> None:
        if obj_no not in self._finished:
            raise ValueError("Cannot retry a job that is not done")
        with self.lock:
            meta = self.meta.setdefault(obj_no, {})
            meta["retry"] = meta.setdefault("retry", 0) + 1
            if meta["retry"] >= 3:
                for case in self._finished[obj_no]:
                    case.status.set("failed", "Maximum number of retries exceeded")
                    case.save()
            else:
                self.buffer[obj_no] = self._finished.pop(obj_no)
                for case in self.buffer[obj_no]:
                    if case.status.value not in ("pending", "ready"):
                        if case.dependencies:
                            case.status.set("pending")
                        else:
                            case.status.set("ready")
                        case.save()

    def put(self, *cases: canary.TestCase) -> None:
        for case in cases:
            if canary.config.get("config:debug"):
                # The case should have already been validated
                check = canary.config.pluginmanager.hook.canary_resources_avail(case=case)
                if not check:
                    raise ValueError(
                        f"Unable to run {case} for the the following reason: {check.reason}"
                    )
            status = case.status
            if status == "skipped":
                case.save()
            elif not case.status.satisfies(("ready", "pending")):
                raise ValueError(f"{case}: case is not ready or pending")
            else:
                self.tmp_buffer.append(case)

    def cases(self) -> list[canary.TestCase]:
        cases: list[canary.TestCase] = []
        cases.extend([case for batch in self.buffer.values() for case in batch])
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        cases.extend([case for batch in self._notrun.values() for case in batch])
        return cases

    def queued(self) -> list[TestBatch]:  # type: ignore[override]
        return list(self.buffer.values())

    def busy(self) -> list[TestBatch]:  # type: ignore[override]
        return list(self._busy.values())

    def finished(self) -> list[TestBatch]:  # type: ignore[override]
        return list(self._finished.values())

    def notrun(self) -> list[TestBatch]:  # type: ignore[override]
        return list(self._notrun.values())

    def failed(self) -> list[canary.TestCase]:
        return [_ for batch in self._finished.values() for _ in batch if _.status != "success"]

    def skip(self, obj_no: int) -> None:
        self._finished[obj_no] = self.buffer.pop(obj_no)
        finished = {case.id: case for case in self._finished[obj_no]}
        for batch in self.buffer.values():
            for case in batch:
                for i, dep in enumerate(case.dependencies):
                    if dep.id in finished:
                        case.dependencies[i] = finished[dep.id]

    def _counts(self) -> tuple[int, int, int]:
        done = sum([len(_) for _ in self.finished()])
        busy = len([len(_) for _ in self.busy()])
        notrun = len([len(_) for _ in self.queued()])
        notrun += len([len(_) for _ in self.notrun()])
        return done, busy, notrun

    def status(self, start: float | None = None) -> str:
        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done, busy, notrun = self._counts()
            total = done + busy + notrun
            for batch in self.finished():
                for case in batch:
                    if case.status.value in ("success", "xdiff", "xfail"):
                        p += 1
                    elif case.status == "diffed":
                        d += 1
                    elif case.status == "timeout":
                        t += 1
                    else:
                        f += 1
            fmt = "%d/%d running, %d/%d done, %d/%d queued "
            if start is not None:
                duration = hhmmss(time.time() - start)
                fmt += f"in {duration} "
            fmt += "(@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout})"
            text = color.colorize(fmt % (busy, total, done, total, notrun, total, p, d, f, t))
            n = color.clen(text)
            header = color.colorize("@*c{%s}" % " status ".center(n + 10, "="))
            footer = color.colorize("@*c{%s}" % "=" * (n + 10))
            pad = color.colorize("@*c{====}")
            string.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        return string.getvalue()
