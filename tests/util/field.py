from __future__ import annotations

from _canary.util.field import Field
from _canary.util.reducer import Reducer
from _canary.util.reducer import concat
from _canary.util.reducer import last_or_none
from _canary.util.reducer import merge_dicts
from _canary.util.reducer import unique


def test_field_last_or_none_default_behavior():
    f = Field(reducer=Reducer("last", last_or_none))
    assert f.eval() is None

    f.add(1)
    assert f.eval() == 1

    f.add(2)
    assert f.eval() == 2


def test_field_respects_testname_filter():
    f = Field(reducer=Reducer("last", last_or_none))
    f.add(1, when={"testname": "a"})
    f.add(2, when={"testname": "b"})

    assert f.eval(family="a") == 1
    assert f.eval(family="b") == 2
    assert f.eval(family="c") is None


def test_field_respects_options_filter():
    f = Field(reducer=Reducer("last", last_or_none))
    f.add(1, when={"options": "dbg"})
    f.add(2, when={"options": "opt"})

    assert f.eval(on_options=["dbg"]) == 1
    assert f.eval(on_options=["opt"]) == 2
    assert f.eval(on_options=["other"]) is None


def test_field_respects_parameters_filter():
    f = Field(reducer=Reducer("last", last_or_none))
    f.add("low", when={"parameters": "a<=1"})
    f.add("high", when={"parameters": "a>1"})

    assert f.eval(parameters={"a": 1}) == "low"
    assert f.eval(parameters={"a": 2}) == "high"
    assert f.eval(parameters={"a": 0}) == "low"


def test_field_merge_dicts():
    f = Field(reducer=Reducer("merge_dicts", merge_dicts))
    f.add({"a": 1})
    f.add({"b": 2})
    f.add({"a": 3})
    assert f.eval() == {"a": 3, "b": 2}


def test_field_unique_list_reducer():
    # Example: keywords-like behavior but using a simple unique reducer over flattened tokens
    # (for real keywords you might store lists and then concat+unique; this keeps test simple)
    f = Field(reducer=Reducer("unique", unique))
    f.add("a")
    f.add("a")
    f.add("b")
    assert f.eval() == ["a", "b"]


def flatten_unique(xss: list[list[str]]) -> list[str]:
    return unique(concat(xss))


def test_field_keywords_style_union():
    f = Field(reducer=Reducer("flatten_unique", flatten_unique))
    f.add(["fast", "regression"])
    f.add(["regression", "nightly"])
    assert f.eval() == ["fast", "regression", "nightly"]
