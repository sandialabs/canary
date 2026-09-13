# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.hash — SHA-256 truncated hashing."""

import hashlib

import pytest

from _canary.util.hash import hashit


def test_hashit_default_length():
    result = hashit("hello")
    assert len(result) == 15


def test_hashit_custom_length():
    assert len(hashit("hello", length=8)) == 8
    assert len(hashit("hello", length=64)) == 64


def test_hashit_zero_length():
    assert hashit("hello", length=0) == ""


def test_hashit_deterministic():
    assert hashit("canary") == hashit("canary")


def test_hashit_different_inputs_differ():
    assert hashit("foo") != hashit("bar")


def test_hashit_matches_sha256():
    s = "test string"
    expected = hashlib.sha256(s.encode("utf-8")).hexdigest()[:15]
    assert hashit(s) == expected


def test_hashit_empty_string():
    result = hashit("")
    assert len(result) == 15
    assert result == hashlib.sha256(b"").hexdigest()[:15]


@pytest.mark.parametrize("s", ["hello", "world", "canary-ci", "123", "a b c"])
def test_hashit_hex_chars_only(s):
    result = hashit(s)
    assert all(c in "0123456789abcdef" for c in result)
