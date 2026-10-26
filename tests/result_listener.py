# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from _canary.persistence.database import ResultListener


class FakeJob:
    def __init__(self, id: str) -> None:
        self.id = id


class FakeQueue:
    def __init__(self) -> None:
        self._batches = [
            [(Path("claimed/1"), FakeJob("job-1"))],
            [(Path("claimed/1"), FakeJob("job-1"))],
            [],
        ]
        self.released: list[list[Path]] = []
        self.acked: list[list[Path]] = []

    def receive(self):
        return self._batches.pop(0)

    def release(self, paths: list[Path]) -> None:
        self.released.append(list(paths))

    def ack(self, paths: list[Path]) -> None:
        self.acked.append(list(paths))


class FakeDB:
    def __init__(self) -> None:
        self.queue = FakeQueue()
        self.calls = 0

    def put_results(self, *objs) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("database is locked")


def test_result_listener_releases_failed_batch_for_retry() -> None:
    listener = object.__new__(ResultListener)
    listener.db = FakeDB()
    listener._processed = set()

    try:
        listener._drain_once()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected first write to fail")

    assert listener.db.queue.released == [[Path("claimed/1")]]
    assert listener.db.queue.acked == []

    drained = listener._drain_once()

    assert drained is True
    assert listener.db.queue.acked == [[Path("claimed/1")]]
    assert listener._processed == {"job-1"}
