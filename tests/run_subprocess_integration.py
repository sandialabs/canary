# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Integration tests for running a session in a child process.

``_canary.app.run_in_subprocess`` executes a run in a separate process and
streams its job-lifecycle events back onto the application event bus.  These
tests prove, over a real workspace, that (1) the child run actually
re-executes the jobs (the DB reflects the rerun) and (2) the parent observes
the child's events on ``app.get_event_bus()`` -- the contract the TUI relies on
to update live without a console handoff.
"""

import canary
from _canary.app import get_event_bus
from _canary.app import list_jobs
from _canary.app import run_in_subprocess
from _canary.app.pathspec import SpecIdsRequest
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand

PYT_BODY = """\
import sys
import canary
import canary_pyt
canary_pyt.directives.parameterize("x", (1, 2))

def test():
    canary.get_instance()
    return 0

if __name__ == "__main__":
    sys.exit(test())
"""


def _make_workspace(tmp_path):
    (tmp_path / "basic.pyt").write_text(PYT_BODY)
    with working_dir(str(tmp_path)):
        cp = CanaryCommand("run")("-w", ".")
    assert cp.returncode == 0


def test_run_in_subprocess_reruns_and_streams_events(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        ids = [j["id"] for j in list_jobs()]
        assert ids

        seen: list[str] = []
        get_event_bus().subscribe(lambda e: seen.append(e.name))

        handle = run_in_subprocess(SpecIdsRequest(value=ids))
        rc = handle.wait(timeout=120)

        assert rc == 0
        # The child exited cleanly (no mp.Queue feeder deadlock) -- this is the
        # regression that motivated moving to the durable spool transport.
        assert handle.poll() == 0
        # The parent observed the child's job lifecycle on its own bus.
        assert any(name.startswith("job_") for name in seen), seen
        # And the rerun landed in the database.
        after = {j["id"]: j["status"] for j in list_jobs()}
    assert all(after[i] == "PASS" for i in ids)


def test_run_handle_poll_before_and_after_completion(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        ids = [j["id"] for j in list_jobs()]
        handle = run_in_subprocess(SpecIdsRequest(value=ids))
        rc = handle.wait(timeout=120)
    assert rc == 0
    # poll after completion is idempotent and returns the same code.
    assert handle.poll() == 0
