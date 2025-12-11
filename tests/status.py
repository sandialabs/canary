# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.status as status


def test_status_0():
    stat = status.Status()
    stat.set(status="FAILED", reason="Just because")

    other = status.Status()
    assert other != stat
    other.set(status="FAILED", reason="Just because")
    assert other == stat

    stat.set(state="READY")
    assert stat == "READY"

    stat.set(state="PENDING")
    assert stat == "PENDING"

    stat.set(state="BROKEN", reason="reason")
    assert stat.category == "BROKEN"
    assert stat.display_name() == "FAILED (BROKEN)"
