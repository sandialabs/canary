# test_status.py
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.status import Category
from _canary.status import Outcome
from _canary.status import Status
from _canary.status import get_category
from _canary.status import get_default_outcome
from _canary.status import get_possible_outcomes


def test_status_set_outcome_infers_category_and_default_code():
    s = Status()
    s.set(outcome="FAILED", reason="Just because")

    assert s.category == Category.FAIL
    assert s.outcome == Outcome.FAILED
    assert s.reason == "Just because"
    assert s.code == int(Outcome.FAILED)


def test_status_category_sets_default_outcome():
    s = Status()

    s.set(category="PASS")
    assert s.category == Category.PASS
    assert s.outcome == Outcome.SUCCESS

    s.set(category="NOTRUN")
    assert s.category == Category.NOTRUN
    assert s.outcome == Outcome.SKIPPED

    s.set(category="ABORTED")
    assert s.category == Category.ABORTED
    assert s.outcome == Outcome.CANCELLED

    s.set(category="FAIL")
    assert s.category == Category.FAIL
    assert s.outcome == Outcome.FAILED  # default FAIL outcome


def test_outcome_infers_category():
    s = Status()

    s.set(outcome="BLOCKED")
    assert s.category == Category.NOTRUN
    assert s.outcome == Outcome.BLOCKED

    s.set(outcome="XFAIL")
    assert s.category == Category.PASS
    assert s.outcome == Outcome.XFAIL


def test_conflicting_category_and_outcome_raises():
    s = Status()
    with pytest.raises(ValueError, match=r"implies category"):
        s.set(category="PASS", outcome="FAILED")


def test_invalid_outcome_for_category_raises():
    s = Status()
    # Force category first, then forbid mismatched outcome by providing both
    with pytest.raises(ValueError, match="Outcome FAILED implies category FAIL, not NOTRUN"):
        s.set(category="NOTRUN", outcome="FAILED")


def test_glyphs_for_common_outcomes():
    s = Status()

    s.set(outcome="TIMEOUT")
    assert s.category == Category.FAIL
    assert s.glyph() == "⏱"
    assert s.code == int(Outcome.TIMEOUT)

    s.set(outcome="CANCELLED")
    assert s.category == Category.ABORTED
    assert s.glyph() == "⊘"
    assert s.code == int(Outcome.CANCELLED)

    s.set(outcome="SKIPPED")
    assert s.category == Category.NOTRUN
    assert s.glyph() == "⊘"
    assert s.code == int(Outcome.SKIPPED)

    s.set(outcome="NONE")
    assert s.category == Category.NONE
    assert s.glyph() == ""


def test_predicates_and_membership_helpers():
    s = Status()

    s.set(outcome="SUCCESS")
    assert s.is_success()
    assert not s.is_failure()
    assert s.outcome in [Outcome.SUCCESS, Outcome.FAILED]

    s.set(outcome="FAILED")
    assert s.is_failure()
    assert s.outcome in (Outcome.FAILED, Outcome.ERROR)
    assert not s.is_success()


def test_code_override_is_respected():
    s = Status()
    s.set(outcome="FAILED", code=123)
    assert s.category == Category.FAIL
    assert s.outcome == Outcome.FAILED
    assert s.code == 123


def test_convenience_constructors():
    s = Status.SUCCESS()
    assert s.category == Category.PASS
    assert s.outcome == Outcome.SUCCESS
    assert s.code == 0

    f = Status.FAILED(reason="nope")
    assert f.category == Category.FAIL
    assert f.outcome == Outcome.FAILED
    assert f.reason == "nope"

    k = Status.SKIPPED(reason="not applicable")
    assert k.category == Category.NOTRUN
    assert k.outcome == Outcome.SKIPPED
    assert k.reason == "not applicable"


def test_outcome_factory_accepts_int_and_name_and_numeric_string():
    assert Outcome.factory(Outcome.TIMEOUT) == Outcome.TIMEOUT
    assert Outcome.factory(68) == Outcome.TIMEOUT
    assert Outcome.factory("TIMEOUT") == Outcome.TIMEOUT
    assert Outcome.factory("68") == Outcome.TIMEOUT


def test_status_set_accepts_enums_directly():
    s = Status()
    s.set(outcome=Outcome.ERROR)
    assert s.category == Category.FAIL
    assert s.outcome == Outcome.ERROR


def test_display_name_styles_and_glyph():
    s = Status()
    s.set(outcome="SUCCESS")
    assert s.display_name() == "PASS (SUCCESS)"
    assert s.display_name(style="rich") == "[bold green]PASS (SUCCESS)[/]"
    assert s.display_name(style="html") == '<font color="#02FE20">PASS (SUCCESS)</font>'
    assert "PASS (SUCCESS)" in s.display_name(glyph=True)


# ---------------------------------------------------------------------------
# Category — all members, colors, legacy compat
# ---------------------------------------------------------------------------


class TestCategoryMembers:
    def test_all_values(self):
        assert Category.PASS.value == "PASS"
        assert Category.FAIL.value == "FAIL"
        assert Category.ABORTED.value == "ABORTED"
        assert Category.NOTRUN.value == "NOTRUN"
        assert Category.NONE.value == "NONE"

    def test_rich_colors(self):
        assert Category.PASS.rich_color() == "bold green"
        assert Category.FAIL.rich_color() == "bold red"
        assert Category.NOTRUN.rich_color() == "bold yellow"
        assert Category.ABORTED.rich_color() == "bold magenta"
        assert Category.NONE.rich_color() == "bold"

    def test_hex_colors(self):
        assert Category.PASS.hex_color() == "#02FE20"
        assert Category.FAIL.hex_color() == "#FF3333"
        assert Category.NOTRUN.hex_color() == "#FEFD02"
        assert Category.ABORTED.hex_color() == "#F202FE"
        assert Category.NONE.hex_color() == ""

    def test_serialize(self):
        assert Category.PASS.__serialize__() == "PASS"
        assert Category.NOTRUN.__serialize__() == "NOTRUN"
        assert Category.ABORTED.__serialize__() == "ABORTED"

    def test_deserialize_plain_string(self):
        assert Category.__deserialize__("PASS") == Category.PASS
        assert Category.__deserialize__("NOTRUN") == Category.NOTRUN
        assert Category.__deserialize__("ABORTED") == Category.ABORTED

    def test_deserialize_legacy_skip_to_notrun(self):
        """'SKIP' must be silently remapped to NOTRUN."""
        assert Category.__deserialize__("SKIP") == Category.NOTRUN
        assert Category.__deserialize__({"value": "SKIP"}) == Category.NOTRUN

    def test_deserialize_legacy_cancel_to_aborted(self):
        """'CANCEL' must be silently remapped to ABORTED."""
        assert Category.__deserialize__("CANCEL") == Category.ABORTED
        assert Category.__deserialize__({"value": "CANCEL"}) == Category.ABORTED

    def test_deserialize_dict_form(self):
        assert Category.__deserialize__({"value": "FAIL"}) == Category.FAIL

    def test_factory_string(self):
        assert Category.factory("pass") == Category.PASS
        assert Category.factory("FAIL") == Category.FAIL

    def test_factory_legacy_skip(self):
        assert Category.factory("SKIP") == Category.NOTRUN
        assert Category.factory("skip") == Category.NOTRUN

    def test_factory_legacy_cancel(self):
        assert Category.factory("CANCEL") == Category.ABORTED
        assert Category.factory("cancel") == Category.ABORTED

    def test_factory_passthrough(self):
        assert Category.factory(Category.PASS) == Category.PASS


# ---------------------------------------------------------------------------
# Outcome — serialize / deserialize / label
# ---------------------------------------------------------------------------


class TestOutcomeSerialize:
    def test_serialize(self):
        assert Outcome.FAILED.__serialize__() == "FAILED"
        assert Outcome.BLOCKED.__serialize__() == "BLOCKED"

    def test_deserialize_name(self):
        assert Outcome.__deserialize__("FAILED") == Outcome.FAILED

    def test_deserialize_int(self):
        assert Outcome.__deserialize__(65) == Outcome.FAILED

    def test_deserialize_int_string(self):
        assert Outcome.__deserialize__("65") == Outcome.FAILED

    def test_deserialize_negative_int_string(self):
        assert Outcome.__deserialize__("-1") == Outcome.NONE

    def test_deserialize_dict_form(self):
        assert Outcome.__deserialize__({"value": 65}) == Outcome.FAILED

    def test_label(self):
        assert Outcome.FAILED.label == "FAILED"
        assert Outcome.SUCCESS.label == "SUCCESS"


# ---------------------------------------------------------------------------
# Status — query methods, reset, from_dict, serialize round-trip
# ---------------------------------------------------------------------------


class TestStatusQueryMethods:
    def test_is_success(self):
        assert Status.SUCCESS().is_success()
        assert not Status.FAILED().is_success()

    def test_is_failure(self):
        assert Status.FAILED().is_failure()
        assert not Status.SUCCESS().is_failure()

    def test_is_skipped_covers_skipped_and_blocked(self):
        assert Status.SKIPPED().is_skipped()
        assert Status.BLOCKED().is_skipped()
        assert not Status.SUCCESS().is_skipped()

    def test_is_cancelled_covers_cancelled_and_interrupted(self):
        assert Status.CANCELLED().is_cancelled()
        assert Status.INTERRUPTED().is_cancelled()
        assert not Status.SUCCESS().is_cancelled()

    def test_is_unset(self):
        assert Status().is_unset()
        assert not Status.SUCCESS().is_unset()

    def test_is_terminal(self):
        assert Status.SUCCESS().is_terminal()
        assert not Status().is_terminal()

    def test_is_blocked(self):
        assert Status.BLOCKED().is_blocked()
        assert not Status.SKIPPED().is_blocked()

    def test_is_diffed(self):
        assert Status.DIFFED().is_diffed()
        assert not Status.FAILED().is_diffed()

    def test_is_failed(self):
        assert Status.FAILED().is_failed()
        assert not Status.DIFFED().is_failed()

    def test_is_error(self):
        assert Status.ERROR().is_error()
        assert not Status.FAILED().is_error()

    def test_is_timeout(self):
        assert Status.TIMEOUT().is_timeout()
        assert not Status.FAILED().is_timeout()

    def test_is_xfail(self):
        s = Status()
        s.set(outcome="XFAIL")
        assert s.is_xfail()
        assert not Status.SUCCESS().is_xfail()

    def test_is_xdiff(self):
        s = Status()
        s.set(outcome="XDIFF")
        assert s.is_xdiff()
        assert not Status.SUCCESS().is_xdiff()

    def test_has_code(self):
        s = Status.FAILED(code=99)
        assert s.has_code(99)
        assert not s.has_code(0)

    def test_returncode_alias(self):
        s = Status.SUCCESS()
        assert s.returncode == s.code == 0


class TestStatusReset:
    def test_reset_clears_all_fields(self):
        s = Status.FAILED(reason="oops", code=99)
        s.reset()
        assert s.category == Category.NONE
        assert s.outcome == Outcome.NONE
        assert s.reason is None
        assert s.code == -1
        assert s.is_unset()


class TestStatusSerialize:
    def test_serialize_round_trip(self):
        original = Status.FAILED(reason="bad", code=65)
        d = original.__serialize__()
        restored = Status.__deserialize__(d)
        assert restored.category == original.category
        assert restored.outcome == original.outcome
        assert restored.reason == original.reason
        assert restored.code == original.code

    def test_serialize_keys(self):
        d = Status.SUCCESS().__serialize__()
        assert set(d.keys()) == {"category", "outcome", "reason", "code"}


class TestStatusFromDict:
    def test_from_dict_basic(self):
        s = Status.from_dict({"category": "FAIL", "outcome": "FAILED", "reason": "x", "code": 1})
        assert s.category == Category.FAIL
        assert s.outcome == Outcome.FAILED
        assert s.reason == "x"
        assert s.code == 1

    def test_from_dict_defaults(self):
        s = Status.from_dict({})
        assert s.is_unset()

    def test_from_dict_legacy_status_key(self):
        """'status' key (legacy) maps to outcome."""
        s = Status.from_dict({"status": "FAILED"})
        assert s.outcome == Outcome.FAILED

    def test_from_dict_legacy_skip_category(self):
        """Legacy 'SKIP' category string is remapped to NOTRUN."""
        s = Status.from_dict({"category": "SKIP", "outcome": "SKIPPED"})
        assert s.category == Category.NOTRUN

    def test_from_dict_legacy_cancel_category(self):
        """Legacy 'CANCEL' category string is remapped to ABORTED."""
        s = Status.from_dict({"category": "CANCEL", "outcome": "CANCELLED"})
        assert s.category == Category.ABORTED

    def test_from_dict_unknown_key_raises(self):
        with pytest.raises(TypeError, match="Unknown kwargs"):
            Status.from_dict({"bogus": "value"})


# ---------------------------------------------------------------------------
# Convenience constructors — complete coverage
# ---------------------------------------------------------------------------


class TestConvenienceConstructors:
    def test_xfail(self):
        s = Status.XFAIL()
        assert s.category == Category.PASS
        assert s.outcome == Outcome.XFAIL

    def test_xdiff(self):
        s = Status.XDIFF()
        assert s.category == Category.PASS
        assert s.outcome == Outcome.XDIFF

    def test_diffed(self):
        s = Status.DIFFED(reason="diff found", code=64)
        assert s.category == Category.FAIL
        assert s.outcome == Outcome.DIFFED
        assert s.reason == "diff found"
        assert s.code == 64

    def test_timeout(self):
        s = Status.TIMEOUT(code=68)
        assert s.category == Category.FAIL
        assert s.outcome == Outcome.TIMEOUT
        assert s.code == 68

    def test_error(self):
        s = Status.ERROR(reason="framework error")
        assert s.category == Category.FAIL
        assert s.outcome == Outcome.ERROR

    def test_broken(self):
        s = Status.BROKEN(reason="inconsistent state")
        assert s.category == Category.FAIL
        assert s.outcome == Outcome.BROKEN

    def test_blocked(self):
        s = Status.BLOCKED(reason="dep failed")
        assert s.category == Category.NOTRUN
        assert s.outcome == Outcome.BLOCKED

    def test_cancelled(self):
        s = Status.CANCELLED(reason="user cancelled")
        assert s.category == Category.ABORTED
        assert s.outcome == Outcome.CANCELLED

    def test_interrupted(self):
        s = Status.INTERRUPTED()
        assert s.category == Category.ABORTED
        assert s.outcome == Outcome.INTERRUPTED
        assert s.reason == "Keyboard interrupt"
        assert s.code > 0  # SIGINT value


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


class TestGetCategory:
    def test_pass_outcomes(self):
        for o in (Outcome.SUCCESS, Outcome.XFAIL, Outcome.XDIFF):
            assert get_category(o) == Category.PASS

    def test_fail_outcomes(self):
        for o in (
            Outcome.DIFFED,
            Outcome.FAILED,
            Outcome.ERROR,
            Outcome.BROKEN,
            Outcome.TIMEOUT,
            Outcome.INVALID,
        ):
            assert get_category(o) == Category.FAIL

    def test_aborted_outcomes(self):
        for o in (Outcome.CANCELLED, Outcome.INTERRUPTED):
            assert get_category(o) == Category.ABORTED

    def test_notrun_outcomes(self):
        for o in (Outcome.SKIPPED, Outcome.BLOCKED):
            assert get_category(o) == Category.NOTRUN

    def test_none_outcome(self):
        assert get_category(Outcome.NONE) == Category.NONE


class TestGetPossibleOutcomes:
    def test_pass(self):
        assert set(get_possible_outcomes(Category.PASS)) == {
            Outcome.SUCCESS,
            Outcome.XFAIL,
            Outcome.XDIFF,
        }

    def test_fail(self):
        assert set(get_possible_outcomes(Category.FAIL)) == {
            Outcome.DIFFED,
            Outcome.FAILED,
            Outcome.ERROR,
            Outcome.BROKEN,
            Outcome.TIMEOUT,
            Outcome.INVALID,
        }

    def test_aborted(self):
        assert set(get_possible_outcomes(Category.ABORTED)) == {
            Outcome.CANCELLED,
            Outcome.INTERRUPTED,
        }

    def test_notrun(self):
        assert set(get_possible_outcomes(Category.NOTRUN)) == {Outcome.SKIPPED, Outcome.BLOCKED}

    def test_none(self):
        assert get_possible_outcomes(Category.NONE) == (Outcome.NONE,)


class TestGetDefaultOutcome:
    def test_pass(self):
        assert get_default_outcome(Category.PASS) == Outcome.SUCCESS

    def test_fail(self):
        assert get_default_outcome(Category.FAIL) == Outcome.FAILED

    def test_aborted(self):
        assert get_default_outcome(Category.ABORTED) == Outcome.CANCELLED

    def test_notrun(self):
        assert get_default_outcome(Category.NOTRUN) == Outcome.SKIPPED

    def test_none(self):
        assert get_default_outcome(Category.NONE) == Outcome.NONE
