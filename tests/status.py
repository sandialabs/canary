# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.status as status


def test_status_0_updated_interface_and_rules():
    stat = status.Status()
    stat.set(outcome="FAILED", reason="Just because")

    # status implies category and terminal state
    assert stat.category == "FAIL"
    assert stat.outcome == "FAILED"
    assert stat.reason == "Just because"
    assert int(stat) == status.Status.CODE_FOR_OUTCOME["FAILED"]

    other = status.Status()
    assert other != stat
    other.set(outcome="FAILED", reason="Just because")
    assert other == stat

    # terminal outcome again
    stat.set(outcome="BROKEN", reason="reason")
    assert stat.category == "FAIL"
    assert stat.outcome == "BROKEN"
    assert stat.display_name() == "FAIL (BROKEN)"


def test_category_sets_default_outcome_and_infers_state():
    s = status.Status()

    s.set(category="PASS")
    assert s.category == "PASS"
    assert s.outcome == "SUCCESS"  # default PASS outcome

    s.set(category="SKIP")
    assert s.category == "SKIP"
    assert s.outcome == "SKIPPED"  # default SKIP outcome

    s.set(category="CANCEL")
    assert s.category == "CANCEL"
    assert s.outcome == "CANCELLED"  # default CANCEL outcome


def test_outcome_infers_category_and_state():
    s = status.Status()

    s.set(outcome="BLOCKED")
    assert s.category == "SKIP"
    assert s.outcome == "BLOCKED"

    s.set(outcome="XFAIL")
    assert s.category == "PASS"
    assert s.outcome == "XFAIL"


def test_lifecycle_state_always_forces_none_none():
    s = status.Status(category="FAIL", outcome="FAILED", reason="x")
    assert s.category == "FAIL"
    assert s.outcome == "FAILED"
    # note: reason is overwritten to whatever was passed to __init__/set
    assert s.display_name() == "FAIL (FAILED)"


def test_conflicting_category_and_outcome_raises():
    s = status.Status()
    with pytest.raises(ValueError, match=r"implies category"):
        s.set(category="PASS", outcome="FAILED")  # FAILED is FAIL-category


def test_display_name_styles_and_glyph():
    s = status.Status()
    s.set(outcome="SUCCESS")
    assert s.display_name() == "PASS (SUCCESS)"
    assert s.display_name(style="rich") == "[bold green]PASS (SUCCESS)[/bold green]"
    assert s.display_name(style="html") == '<font color="#02FE20">PASS (SUCCESS)</font>'
    assert s.display_name(glyph=True) == "✓ PASS (SUCCESS)"


def test_codes_and_glyphs_for_outcomes():
    s = status.Status()

    s.set(outcome="TIMEOUT")
    assert s.category == "FAIL"
    assert s.glyph == "⏱"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["TIMEOUT"]

    s.set(outcome="CANCELLED")
    assert s.category == "CANCEL"
    assert s.glyph == "⊘"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["CANCELLED"]

    s.set(outcome="SKIPPED")
    assert s.category == "SKIP"
    assert s.glyph == "⊘"
    assert int(s) == status.Status.CODE_FOR_OUTCOME["SKIPPED"]


def test_from_dict_round_trip_uses_validation():
    s = status.Status()
    s.set(outcome="XDIFF", reason="expected diff")
    d = s.asdict()

    s2 = status.Status.from_dict(d)
    assert s2 == s
    assert s2.category == "PASS"
    assert s2.outcome == "XDIFF"
    assert s2.reason == "expected diff"


def test_convenience_constructors():
    s = status.Status.SUCCESS()
    assert s.category == "PASS"
    assert s.outcome == "SUCCESS"
    assert int(s) == 0

    f = status.Status.FAILED(reason="nope")
    assert f.category == "FAIL"
    assert f.outcome == "FAILED"
    assert f.reason == "nope"

    k = status.Status.SKIPPED(reason="not applicable")
    assert k.category == "SKIP"
    assert k.outcome == "SKIPPED"
