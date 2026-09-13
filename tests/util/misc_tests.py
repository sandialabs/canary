# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.misc — pure utility functions."""

from argparse import Namespace
from types import SimpleNamespace

import pytest

from _canary.util.misc import argsort
from _canary.util.misc import boolean
from _canary.util.misc import dedup
from _canary.util.misc import digits
from _canary.util.misc import ns2dict
from _canary.util.misc import partition

# ---------------------------------------------------------------------------
# boolean
# ---------------------------------------------------------------------------


def test_boolean_none_is_false():
    assert boolean(None) is False


def test_boolean_true_passes_through():
    assert boolean(True) is True


def test_boolean_false_passes_through():
    assert boolean(False) is False


def test_boolean_zero_int():
    assert boolean(0) is False


def test_boolean_nonzero_int():
    assert boolean(1) is True
    assert boolean(42) is True


@pytest.mark.parametrize("s", ["0", "off", "false", "no", "OFF", "FALSE", "NO"])
def test_boolean_falsy_strings(s):
    assert boolean(s) is False


@pytest.mark.parametrize("s", ["1", "on", "true", "yes", "YES", "True", "hello"])
def test_boolean_truthy_strings(s):
    assert boolean(s) is True


def test_boolean_empty_string_is_truthy():
    # empty string does not appear in the falsy set ("0","off","false","no")
    # so boolean("") falls through to bool("") == False … wait, actually
    # the implementation calls: arg.lower() not in ("0","off","false","no")
    # "" is not in that set → True. This is intentional behaviour.
    assert boolean("") is True


# ---------------------------------------------------------------------------
# ns2dict
# ---------------------------------------------------------------------------


def test_ns2dict_simple_namespace():
    ns = SimpleNamespace(a=1, b="hello")
    d = ns2dict(ns)
    assert d == {"a": 1, "b": "hello"}


def test_ns2dict_argparse_namespace():
    ns = Namespace(x=10, y=20)
    d = ns2dict(ns)
    assert d == {"x": 10, "y": 20}


def test_ns2dict_nested():
    inner = SimpleNamespace(c=3)
    outer = SimpleNamespace(a=1, b=inner)
    d = ns2dict(outer)
    assert d == {"a": 1, "b": {"c": 3}}


def test_ns2dict_deeply_nested():
    deep = SimpleNamespace(z=99)
    mid = SimpleNamespace(y=deep)
    top = SimpleNamespace(x=mid)
    d = ns2dict(top)
    assert d == {"x": {"y": {"z": 99}}}


def test_ns2dict_non_namespace_values_unchanged():
    ns = SimpleNamespace(lst=[1, 2, 3], tup=(4, 5))
    d = ns2dict(ns)
    assert d["lst"] == [1, 2, 3]
    assert d["tup"] == (4, 5)


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------


def test_dedup_empty():
    assert dedup([]) == []


def test_dedup_no_duplicates():
    assert dedup([1, 2, 3]) == [1, 2, 3]


def test_dedup_all_duplicates():
    assert dedup([5, 5, 5]) == [5]


def test_dedup_preserves_order():
    assert dedup([3, 1, 2, 1, 3]) == [3, 1, 2]


def test_dedup_strings():
    assert dedup(["a", "b", "a", "c"]) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# digits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "x, expected", [(0, 1), (1, 1), (9, 1), (10, 2), (99, 2), (100, 3), (999, 3), (1000, 4)]
)
def test_digits(x, expected):
    assert digits(x) == expected


# ---------------------------------------------------------------------------
# partition
# ---------------------------------------------------------------------------


def test_partition_empty():
    yes, no = partition([], lambda x: x > 0)
    assert yes == []
    assert no == []


def test_partition_all_match():
    yes, no = partition([1, 2, 3], lambda x: x > 0)
    assert yes == [1, 2, 3]
    assert no == []


def test_partition_none_match():
    yes, no = partition([1, 2, 3], lambda x: x > 10)
    assert yes == []
    assert no == [1, 2, 3]


def test_partition_mixed():
    yes, no = partition([1, -2, 3, -4, 5], lambda x: x > 0)
    assert yes == [1, 3, 5]
    assert no == [-2, -4]


def test_partition_strings():
    yes, no = partition(["apple", "banana", "apricot", "cherry"], lambda s: s.startswith("a"))
    assert yes == ["apple", "apricot"]
    assert no == ["banana", "cherry"]


# ---------------------------------------------------------------------------
# argsort
# ---------------------------------------------------------------------------


def test_argsort_already_sorted():
    assert argsort([1, 2, 3]) == [0, 1, 2]


def test_argsort_reverse_sorted():
    assert argsort([3, 2, 1]) == [2, 1, 0]


def test_argsort_mixed():
    seq = [30, 10, 20]
    indices = argsort(seq)
    assert [seq[i] for i in indices] == [10, 20, 30]


def test_argsort_empty():
    assert argsort([]) == []


def test_argsort_single():
    assert argsort([42]) == [0]


def test_argsort_strings():
    seq = ["banana", "apple", "cherry"]
    indices = argsort(seq)
    assert [seq[i] for i in indices] == ["apple", "banana", "cherry"]
