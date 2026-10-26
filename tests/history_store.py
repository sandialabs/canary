# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.history.store import HistoryStore


class FakeJob:
    def __init__(self, id: str) -> None:
        self.id = id


def test_load_skips_corrupt_history_lines(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    job = FakeJob("ab" + "c" * 62)
    path = store.path_for(job)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"what": "meta", "x": 1}\nnot-json\n{"what": "record", "status": "pass"}\n')

    history = store.load(job)

    assert history == {"meta": {"x": 1}, "records": [{"status": "pass"}]}
