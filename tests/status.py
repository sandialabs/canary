# test_status.py
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.status as status


def test_status_set_outcome_infers_category_and_default_code():
    s = status.Status()
    s.set(outcome="FAILED", reason="Just because")

    assert s.category is status.Category.FAIL
    assert s.outcome is status.Outcome.FAILED
    assert s.reason == "Just because"
    assert s.code == int(status.Outcome.FAILED)


def test_status_category_sets_default_outcome():
    s = status.Status()

    s.set(category="PASS")
    assert s.category is status.Category.PASS
    assert s.outcome is status.Outcome.SUCCESS

    s.set(category="SKIP")
    assert s.category is status.Category.SKIP
    assert s.outcome is status.Outcome.SKIPPED

    s.set(category="CANCEL")
    assert s.category is status.Category.CANCEL
    assert s.outcome is status.Outcome.CANCELLED

    s.set(category="FAIL")
    assert s.category is status.Category.FAIL
    assert s.outcome is status.Outcome.DIFFED  # default FAIL outcome per implementation


def test_outcome_infers_category():
    s = status.Status()

    s.set(outcome="BLOCKED")
    assert s.category is status.Category.SKIP
    assert s.outcome is status.Outcome.BLOCKED

    s.set(outcome="XFAIL")
    assert s.category is status.Category.PASS
    assert s.outcome is status.Outcome.XFAIL


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
    assert s.category is status.Category.FAIL
    assert s.glyph() == "⏱"
    assert s.code == int(status.Outcome.TIMEOUT)

    s.set(outcome="CANCELLED")
    assert s.category is status.Category.CANCEL
    assert s.glyph() == "⊘"
    assert s.code == int(status.Outcome.CANCELLED)

    s.set(outcome="SKIPPED")
    assert s.category is status.Category.SKIP
    assert s.glyph() == "⊘"
    assert s.code == int(status.Outcome.SKIPPED)

    s.set(outcome="NONE")
    assert s.category is status.Category.NONE
    assert s.glyph() == ""


def test_predicates_and_membership_helpers():
    s = status.Status()

    s.set(outcome="SUCCESS")
    assert s.is_success()
    assert not s.is_failure()
    assert s.has_category("PASS")
    assert s.has_outcome("SUCCESS")
    assert s.outcome_in(["SUCCESS", "FAILED"])
    assert s.category_in(["PASS", "FAIL"])

    s.set(outcome="FAILED")
    assert s.is_failure()
    assert s.outcome_in([status.Outcome.FAILED, "ERROR"])
    assert not s.category_in(["PASS", "SKIP"])


def test_code_override_is_respected():
    s = status.Status()
    s.set(outcome="FAILED", code=123)
    assert s.category is status.Category.FAIL
    assert s.outcome is status.Outcome.FAILED
    assert s.code == 123


def test_convenience_constructors():
    s = status.Status.SUCCESS()
    assert s.category is status.Category.PASS
    assert s.outcome is status.Outcome.SUCCESS
    assert s.code == 0

    f = status.Status.FAILED(reason="nope")
    assert f.category is status.Category.FAIL
    assert f.outcome is status.Outcome.FAILED
    assert f.reason == "nope"

    k = status.Status.SKIPPED(reason="not applicable")
    assert k.category is status.Category.SKIP
    assert k.outcome is status.Outcome.SKIPPED
    assert k.reason == "not applicable"


def test_outcome_factory_accepts_int_and_name_and_numeric_string():
    assert status.Outcome.factory(status.Outcome.TIMEOUT) is status.Outcome.TIMEOUT
    assert status.Outcome.factory(68) is status.Outcome.TIMEOUT
    assert status.Outcome.factory("TIMEOUT") is status.Outcome.TIMEOUT
    assert status.Outcome.factory("68") is status.Outcome.TIMEOUT


def test_status_set_accepts_enums_directly():
    s = status.Status()
    s.set(outcome=status.Outcome.ERROR)
    assert s.category is status.Category.FAIL
    assert s.outcome is status.Outcome.ERROR


def test_display_name_styles_and_glyph():
    s = status.Status()
    s.set(outcome="SUCCESS")
    assert s.display_name() == "PASS (SUCCESS)"
    assert s.display_name(style="rich") == "[bold green]PASS (SUCCESS)[/]"
    assert s.display_name(style="html") == '<font color="#02FE20">PASS (SUCCESS)</font>'
    assert s.display_name(glyph=True) == "✓ PASS (SUCCESS)"
