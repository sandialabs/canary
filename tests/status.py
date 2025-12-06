# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.status as status
from _canary.error import diff_exit_status
from _canary.error import fail_exit_status
from _canary.error import skip_exit_status
from _canary.error import timeout_exit_status


def test_status_0():
    stat = status.Status()
    stat.set("failed", message="Just because")

    other = status.Status()
    assert other != stat
    other.set("failed", message="Just because")
    assert other == stat

    stat.set("ready")
    assert stat == "READY"

    stat.set("pending")
    assert stat == "PENDING"

    stat.set(0)
    assert stat == "SUCCESS"
    stat.set(diff_exit_status)
    assert stat == "DIFFED"
    stat.set(skip_exit_status)
    assert stat == "SKIPPED"
    stat.set(fail_exit_status)
    assert stat == "FAILED"
    stat.set(timeout_exit_status)
    assert stat == "TIMEOUT"
    stat.set(66)
    assert stat == "TIMEOUT"
    stat.set(22)
    assert stat == "FAILED"

    stat.set("broken", message="reason")
    assert stat.name == "BROKEN"
    assert stat.display_name() == "BROKEN"
