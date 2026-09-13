# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.singleton — lazy-initialized singleton proxy."""

import pytest

from _canary.util.singleton import Singleton


class _Counter:
    """Simple callable class that counts how many times it has been created."""

    instances = 0

    def __init__(self, value=42):
        _Counter.instances += 1
        self.value = value
        self._data = {"key": "val"}
        self._items = [10, 20, 30]

    def __call__(self, x):
        return x * 2

    def __iter__(self):
        return iter(self._items)

    def __contains__(self, item):
        return item in self._items

    def __getitem__(self, key):
        return self._data[key]

    def __str__(self):
        return f"Counter({self.value})"

    def __repr__(self):
        return f"Counter(value={self.value!r})"


def setup_function():
    _Counter.instances = 0


def test_singleton_lazy_init():
    """Factory is not called until first access."""
    calls = []
    s = Singleton(lambda: calls.append(1) or _Counter())
    assert calls == []
    _ = s.value
    assert calls == [1]


def test_singleton_factory_called_once():
    """Factory is called exactly once even with multiple accesses."""
    s = Singleton(_Counter)
    _ = s.value
    _ = s.value
    _ = s.value
    assert _Counter.instances == 1


def test_singleton_getattr_proxy():
    s = Singleton(lambda: _Counter(99))
    assert s.value == 99


def test_singleton_getitem():
    s = Singleton(_Counter)
    assert s["key"] == "val"


def test_singleton_contains():
    s = Singleton(_Counter)
    assert 10 in s
    assert 99 not in s


def test_singleton_call():
    s = Singleton(_Counter)
    assert s(5) == 10


def test_singleton_iter():
    s = Singleton(_Counter)
    assert list(s) == [10, 20, 30]


def test_singleton_str():
    s = Singleton(lambda: _Counter(7))
    assert str(s) == "Counter(7)"


def test_singleton_repr():
    s = Singleton(lambda: _Counter(7))
    assert repr(s) == "Counter(value=7)"


def test_singleton_instance_property():
    s = Singleton(_Counter)
    inst = s.instance
    assert isinstance(inst, _Counter)
    assert s.instance is inst  # same object returned twice


def test_singleton_getattr_guards_instance_before_init():
    """Accessing _instance or instance before init should raise AttributeError, not recurse."""
    s = object.__new__(Singleton)
    # _instance not yet set; __getattr__ guard should raise AttributeError, not recurse
    with pytest.raises(AttributeError):
        _ = s.instance
