# test_status.py
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.status as status


def test_status_set_outcome_infers_category_and_default_code():
    s = status.Status()
    s.set(outcome="FAILED", reason="Just because")

    assert s.category == status.Category.FAIL
    assert s.outcome == status.Outcome.FAILED
    assert s.reason == "Just because"
    assert s.code == int(status.Outcome.FAILED)


def test_status_category_sets_default_outcome():
    s = status.Status()

    s.set(category="PASS")
    assert s.category == status.Category.PASS
    assert s.outcome == status.Outcome.SUCCESS

    s.set(category="SKIP")
    assert s.category == status.Category.SKIP
    assert s.outcome == status.Outcome.SKIPPED

    s.set(category="CANCEL")
    assert s.category == status.Category.CANCEL
    assert s.outcome == status.Outcome.CANCELLED

    s.set(category="FAIL")
    assert s.category == status.Category.FAIL
    assert s.outcome == status.Outcome.DIFFED  # default FAIL outcome per implementation


def test_outcome_infers_category():
    s = status.Status()

    s.set(outcome="BLOCKED")
    assert s.category == status.Category.SKIP
    assert s.outcome == status.Outcome.BLOCKED

    s.set(outcome="XFAIL")
    assert s.category == status.Category.PASS
    assert s.outcome == status.Outcome.XFAIL


def test_conflicting_category_and_outcome_raises():
    s = status.Status()
    with pytest.raises(ValueError, match=r"implies category"):
        s.set(category="PASS", outcome="FAILED")


def test_invalid_outcome_for_category_raises():
    s = status.Status()
    # Force category first, then forbid mismatched outcome by providing both
    with pytest.raises(ValueError, match="Outcome FAILED implies category FAIL, not SKIP"):
        s.set(category="SKIP", outcome="FAILED")


def test_glyphs_for_common_outcomes():
    s = status.Status()

    s.set(outcome="TIMEOUT")
    assert s.category == status.Category.FAIL
    assert s.glyph() == "⏱"
    assert s.code == int(status.Outcome.TIMEOUT)

    s.set(outcome="CANCELLED")
    assert s.category == status.Category.CANCEL
    assert s.glyph() == "⊘"
    assert s.code == int(status.Outcome.CANCELLED)

    s.set(outcome="SKIPPED")
    assert s.category == status.Category.SKIP
    assert s.glyph() == "⊘"
    assert s.code == int(status.Outcome.SKIPPED)

    s.set(outcome="NONE")
    assert s.category == status.Category.NONE
    assert s.glyph() == ""


def test_predicates_and_membership_helpers():
    s = status.Status()

    s.set(outcome="SUCCESS")
    assert s.is_success()
    assert not s.is_failure()
    assert s.outcome in [status.Outcome.SUCCESS, status.Outcome.FAILED]

    s.set(outcome="FAILED")
    assert s.is_failure()
    assert s.outcome in (status.Outcome.FAILED, status.Outcome.ERROR)
    assert not s.is_success()


def test_code_override_is_respected():
    s = status.Status()
    s.set(outcome="FAILED", code=123)
    assert s.category == status.Category.FAIL
    assert s.outcome == status.Outcome.FAILED
    assert s.code == 123


def test_convenience_constructors():
    s = status.Status.SUCCESS()
    assert s.category == status.Category.PASS
    assert s.outcome == status.Outcome.SUCCESS
    assert s.code == 0

    f = status.Status.FAILED(reason="nope")
    assert f.category == status.Category.FAIL
    assert f.outcome == status.Outcome.FAILED
    assert f.reason == "nope"

    k = status.Status.SKIPPED(reason="not applicable")
    assert k.category == status.Category.SKIP
    assert k.outcome == status.Outcome.SKIPPED
    assert k.reason == "not applicable"


def test_outcome_factory_accepts_int_and_name_and_numeric_string():
    assert status.Outcome.factory(status.Outcome.TIMEOUT) == status.Outcome.TIMEOUT
    assert status.Outcome.factory(68) == status.Outcome.TIMEOUT
    assert status.Outcome.factory("TIMEOUT") == status.Outcome.TIMEOUT
    assert status.Outcome.factory("68") == status.Outcome.TIMEOUT


def test_status_set_accepts_enums_directly():
    s = status.Status()
    s.set(outcome=status.Outcome.ERROR)
    assert s.category == status.Category.FAIL
    assert s.outcome == status.Outcome.ERROR


def test_display_name_styles_and_glyph():
    s = status.Status()
    s.set(outcome="SUCCESS")
    assert s.display_name() == "PASS (SUCCESS)"
    assert s.display_name(style="rich") == "[bold green]PASS (SUCCESS)[/]"
    assert s.display_name(style="html") == '<font color="#02FE20">PASS (SUCCESS)</font>'
    assert s.display_name(glyph=True) == "✓ PASS (SUCCESS)"
