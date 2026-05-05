from _canary.util.reducer import ALL
from _canary.util.reducer import ANY
from _canary.util.reducer import FIRST
from _canary.util.reducer import IDENTITY
from _canary.util.reducer import LAST
from _canary.util.reducer import Reducer
from _canary.util.reducer import concat
from _canary.util.reducer import first_or_none
from _canary.util.reducer import identity
from _canary.util.reducer import last_or_none
from _canary.util.reducer import merge_dicts
from _canary.util.reducer import unique


def test_reducer_is_callable():
    r = Reducer("x", lambda xs: len(xs))
    assert r([1, 2, 3]) == 3
    assert r.name == "x"


def test_last_or_none():
    assert last_or_none([]) is None
    assert last_or_none([1]) == 1
    assert last_or_none([1, 2]) == 2
    assert LAST([1, 2, 3]) == 3


def test_first_or_none():
    assert first_or_none([]) is None
    assert first_or_none([1]) == 1
    assert first_or_none([1, 2]) == 1
    assert FIRST([1, 2, 3]) == 1


def test_any_true():
    assert ANY([]) is False
    assert ANY([False]) is False
    assert ANY([False, True]) is True


def test_all_true():
    assert ALL([]) is False
    assert ALL([True]) is True
    assert ALL([True, True]) is True
    assert ALL([True, False]) is False


def test_identity():
    xs = [1, 2, 3]
    assert identity(xs) is xs  # identity() returns same list object
    assert IDENTITY(xs) == [1, 2, 3]


def test_concat():
    assert concat([[1, 2], [3], []]) == [1, 2, 3]
    assert concat([("a", "b"), ("c",)]) == ["a", "b", "c"]


def test_unique_preserves_order():
    assert unique([1, 2, 1, 3, 2]) == [1, 2, 3]
    assert unique(["a", "a", "b"]) == ["a", "b"]


def test_merge_dicts_last_wins():
    assert merge_dicts([]) == {}
    assert merge_dicts([{"a": 1}, {"b": 2}]) == {"a": 1, "b": 2}
    assert merge_dicts([{"a": 1}, {"a": 2}]) == {"a": 2}
