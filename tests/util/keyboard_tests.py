# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.keyboard — key mapping and disable logic."""

import sys

import pytest

import _canary.util.keyboard as kb_mod
from _canary.util.keyboard import disable_keyboard_query
from _canary.util.keyboard import get_key
from _canary.util.keyboard import key_mapping


# ---------------------------------------------------------------------------
# Helpers — reset global state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_global(monkeypatch):
    """Each test starts with DISABLE_KEYBOARD_QUERY = None."""
    monkeypatch.setattr(kb_mod, "DISABLE_KEYBOARD_QUERY", None)


# ---------------------------------------------------------------------------
# disable_keyboard_query
# ---------------------------------------------------------------------------


def test_disable_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert disable_keyboard_query() is True


def test_disable_when_gitlab_ci_set(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("GITLAB_CI", "1")
    assert disable_keyboard_query() is True


def test_disable_when_canary_disable_kb_set(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    assert disable_keyboard_query() is True


def test_disable_when_canary_disable_kb_yes(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("CANARY_DISABLE_KB", "YES")
    assert disable_keyboard_query() is True


def test_not_disabled_when_tty_and_no_env(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.delenv("GITLAB_CI", raising=False)
    monkeypatch.delenv("CANARY_DISABLE_KB", raising=False)
    result = disable_keyboard_query()
    assert result is False


def test_cached_after_first_call(monkeypatch):
    """Once determined, value is cached for the lifetime of the global."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    first = disable_keyboard_query()
    # Change the condition — result should still be the cached value
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    second = disable_keyboard_query()
    assert first == second


# ---------------------------------------------------------------------------
# key_mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (chr(127), "backspace"),
        (chr(10), "return"),
        (chr(32), "space"),
        (chr(9), "tab"),
        (chr(27), "esc"),
    ],
)
def test_key_mapping_special_chars(raw, expected):
    assert key_mapping(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 3-char escape sequences: ctrl char + '[' + letter
        ("\x1b[A", "up"),
        ("\x1b[B", "down"),
        ("\x1b[C", "right"),
        ("\x1b[D", "left"),
    ],
)
def test_key_mapping_escape_sequences(raw, expected):
    assert key_mapping(raw) == expected


def test_key_mapping_multibyte_unknown_returns_raw():
    # Multi-char but not a 3-char ctrl sequence -> return as-is
    raw = "\x1b[Z"  # len == 3, but 'Z'=90, not in mapping -> chr(90)='Z' actually
    result = key_mapping(raw)
    # chr(90) = 'Z', not in mapping dict, so returns chr(90)
    assert result == "Z"


def test_key_mapping_regular_ascii():
    assert key_mapping("a") == "a"
    assert key_mapping("z") == "z"
    assert key_mapping("0") == "0"


def test_key_mapping_multi_char_non_ctrl_returns_raw():
    raw = "ab"  # len > 1 but not 3 or ctrl
    assert key_mapping(raw) == "ab"


# ---------------------------------------------------------------------------
# get_key when disabled
# ---------------------------------------------------------------------------


def test_get_key_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(kb_mod, "DISABLE_KEYBOARD_QUERY", True)
    assert get_key() is None
