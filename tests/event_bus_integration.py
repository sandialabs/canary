# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Lifecycle events reach the app event bus during a real run.

The executor publishes its job-lifecycle events to the application
:class:`~_canary.events.EventBus` in addition to invoking its existing
listeners.  This exercises the full path (``Workspace.run`` ->
``canary_runtests`` -> ``ResourceQueueExecutor``) and asserts a subscriber sees
the healthy-job progression with the job carried on each event.
"""

import argparse

import canary
from _canary import app
from _canary.events import Event
from _canary.session.workspace import Workspace
from _canary.util.filesystem import working_dir

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


def test_run_publishes_job_lifecycle_events_to_bus(tmp_path):
    (tmp_path / "t.pyt").write_text(PYT_BODY)

    received: list[Event] = []
    bus = app.get_event_bus()
    sub = bus.subscribe(received.append)
    try:
        with working_dir(tmp_path), canary.config.override() as cfg:
            workspace = Workspace.create(tmp_path)
            specs = workspace.collect({str(tmp_path): []})
            cfg.options = argparse.Namespace()
            workspace.run(specs, only="all")
    finally:
        bus.unsubscribe(sub)

    names = [e.name for e in received]
    # A healthy job passes through submit -> start -> finish in order.
    for expected in ("job_submitted", "job_started", "job_finished"):
        assert expected in names, f"missing {expected}; saw {names}"
    assert names.index("job_submitted") < names.index("job_started") < names.index("job_finished")

    # Each lifecycle event carries a primitives-only JobEvent projection -- no
    # _canary runtime object crosses the bus (the interface boundary contract).
    finished = next(e for e in received if e.name == "job_finished")
    job_event = finished.payload["job"]
    assert isinstance(job_event, dict)
    assert job_event["phase"] == "DONE"
    assert job_event["status"] == "PASS"
    assert isinstance(job_event["id"], str) and job_event["id"]
    assert all(not type(v).__module__.startswith("_canary") for v in job_event.values())
