# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.status as status


def test_status_0_updated_interface_and_rules():
    stat = status.Status()
    stat.set(status="FAILED", reason="Just because")

    # status implies category and terminal state
    assert stat.state == "COMPLETE"
    assert stat.category == "FAIL"
    assert stat.status == "FAILED"
    assert stat.reason == "Just because"
    assert int(stat) == status.Status.CODE_FOR_OUTCOME["FAILED"]

    other = status.Status()
    assert other != stat
    other.set(status="FAILED", reason="Just because")
    assert other == stat

    # lifecycle states override category/outcome
    stat.set(state="READY")
    assert stat == "READY"
    assert stat.state == "READY"
    assert stat.category == "NONE"
    assert stat.status == "NONE"
    assert stat.display_name() == "READY"

    stat.set(state="PENDING")
    assert stat == "PENDING"
    assert stat.display_name() == "PENDING"

    # terminal outcome again
    stat.set(status="BROKEN", reason="reason")
    assert stat.state == "COMPLETE"
    assert stat.category == "FAIL"
    assert stat.status == "BROKEN"
    assert stat.display_name() == "FAIL (BROKEN)"


def test_category_sets_default_outcome_and_infers_state():
    s = status.Status()

    s.set(category="PASS")
    assert s.state == "COMPLETE"
    assert s.category == "PASS"
    assert s.status == "SUCCESS"  # default PASS outcome

    s.set(category="SKIP")
    assert s.state == "NOTRUN"
    assert s.category == "SKIP"
    assert s.status == "SKIPPED"  # default SKIP outcome

    s.set(category="CANCEL")
    assert s.state == "COMPLETE"
    assert s.category == "CANCEL"
    assert s.status == "CANCELLED"  # default CANCEL outcome


def test_outcome_infers_category_and_state():
    s = status.Status()

    s.set(status="BLOCKED")
    assert s.state == "NOTRUN"
    assert s.category == "SKIP"
    assert s.status == "BLOCKED"

    s.set(status="XFAIL")
    assert s.state == "COMPLETE"
    assert s.category == "PASS"
    assert s.status == "XFAIL"


def test_lifecycle_state_always_forces_none_none():
    s = status.Status(state="RUNNING", category="FAIL", status="FAILED", reason="x")
    assert s.state == "RUNNING"
    assert s.category == "NONE"
    assert s.status == "NONE"
    # note: reason is overwritten to whatever was passed to __init__/set
    assert s.display_name() == "RUNNING"


def test_conflicting_category_and_outcome_raises():
    s = status.Status()
    with pytest.raises(ValueError, match=r"implies category"):
        s.set(category="PASS", status="FAILED")  # FAILED is FAIL-category


def test_conflicting_terminal_state_and_category_raises():
    s = status.Status()

    # category SKIP implies NOTRUN; asking for COMPLETE should error
    with pytest.raises(ValueError, match=r"implies state"):
        s.set(state="COMPLETE", category="SKIP")

    # category PASS implies COMPLETE; asking for NOTRUN should error
    with pytest.raises(ValueError, match=r"implies state"):
        s.set(state="NOTRUN", category="PASS")


def test_display_name_styles_and_glyph():
    s = status.Status(state="PENDING")
    assert s.display_name() == "PENDING"
    assert s.display_name(style="rich") == "[bold]PENDING[/bold]"
    assert s.display_name(style="html") == "PENDING"
    assert s.display_name(glyph=True) == "○ PENDING"

    s.set(state="RUNNING")
    assert s.display_name() == "RUNNING"
    assert s.display_name(glyph=True) == "▶ RUNNING"

    s.set(status="SUCCESS")
    assert s.display_name() == "PASS (SUCCESS)"
    assert s.display_name(style="rich") == "[bold green]PASS (SUCCESS)[/bold green]"
    assert s.display_name(style="html") == '<font color="#02FE20">PASS (SUCCESS)</font>'
    assert s.display_name(glyph=True) == "✓ PASS (SUCCESS)"


def test_codes_and_glyphs_for_outcomes():
    s = status.Status()

    s.set(status="TIMEOUT")
    assert s.category == "FAIL"
    assert s.state == "COMPLETE"
    assert s.glyph == "⏱"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["TIMEOUT"]

    s.set(status="CANCELLED")
    assert s.category == "CANCEL"
    assert s.state == "COMPLETE"
    assert s.glyph == "⊘"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["CANCELLED"]

    s.set(status="SKIPPED")
    assert s.category == "SKIP"
    assert s.state == "NOTRUN"
    assert s.glyph == "⊘"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["SKIPPED"]


def test_from_dict_round_trip_uses_validation():
    s = status.Status()
    s.set(status="XDIFF", reason="expected diff")
    d = s.asdict()

    s2 = status.Status.from_dict(d)
    assert s2 == s
    assert s2.state == "COMPLETE"
    assert s2.category == "PASS"
    assert s2.status == "XDIFF"
    assert s2.reason == "expected diff"


def test_convenience_constructors():
    assert status.Status.PENDING() == "PENDING"
    assert status.Status.READY() == "READY"
    assert status.Status.RUNNING() == "RUNNING"

    s = status.Status.SUCCESS()
    assert s.state == "COMPLETE"
    assert s.category == "PASS"
    assert s.status == "SUCCESS"
    assert int(s) == 0

    f = status.Status.FAILED(reason="nope")
    assert f.category == "FAIL"
    assert f.status == "FAILED"
    assert f.reason == "nope"

    k = status.Status.SKIPPED(reason="not applicable")
    assert k.state == "NOTRUN"
    assert k.category == "SKIP"
    assert k.status == "SKIPPED"
