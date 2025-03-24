import sys

import pytest

from _canary.when import InvalidSyntax
from _canary.when import When


def test_when_platform():
    expr = When.from_string(f"platform={sys.platform}")
    assert expr.evaluate().value is True
    expr = When.from_string(f"platform='not {sys.platform}'")
    assert expr.evaluate().value is False

    with pytest.raises((InvalidSyntax, IndexError)):
        expr = When.from_string("platform='linux")
        expr.evaluate()


def test_when_name():
    expr = When.from_string("name=spam")
    assert expr.evaluate().value is False
    assert expr.evaluate(testname="spam").value is True


def test_when_options():
    expr = When.from_string("options='spam'")
    assert expr.evaluate(on_options=["spam"]).value is True
    assert expr.evaluate().value is False

    expr = When.from_string("options='spam and baz'")
    assert expr.evaluate(on_options=["spam", "baz"]).value is True
    assert expr.evaluate().value is False
    assert expr.evaluate(on_options=["spam"]).value is False
    assert expr.evaluate(on_options=["baz"]).value is False

    expr = When.from_string("options='spam or baz'")
    assert expr.evaluate(on_options=["spam", "baz"]).value is True
    assert expr.evaluate().value is False
    assert expr.evaluate(on_options=["spam"]).value is True
    assert expr.evaluate(on_options=["baz"]).value is True


def test_when_parameters():
    expr = When.from_string("parameters='cpus<4'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"cpus": 1}).value is True
    assert expr.evaluate(parameters={"cpus": 5}).value is False

    expr = When.from_string("parameters='cpus> 2 and cpus<6'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"cpus": 3}).value is True
    assert expr.evaluate(parameters={"cpus": 7}).value is False

    expr = When.from_string("parameters='!cpus'")
    assert expr.evaluate().value is True
    assert expr.evaluate(parameters={"cpus": 4}).value is False
    assert expr.evaluate(parameters={"spam": "baz"}).value is True

    expr = When.from_string("parameters='cpus>2 and baz=spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"cpus": 3}).value is False
    assert expr.evaluate(parameters={"cpus": 3, "baz": "wubble"}).value is False
    assert expr.evaluate(parameters={"cpus": 3, "baz": "spam"}).value is True

    expr = When.from_string("parameters='cpus>2 or baz=spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"cpus": 3}).value is True
    assert expr.evaluate(parameters={"cpus": 3, "baz": "wubble"}).value is True
    assert expr.evaluate(parameters={"cpus": 3, "baz": "spam"}).value is True

    expr = When.from_string("parameters='cpus>2 or baz==spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"cpus": 3}).value is True
    assert expr.evaluate(parameters={"cpus": 3, "baz": "wubble"}).value is True
    assert expr.evaluate(parameters={"cpus": 3, "baz": "spam"}).value is True


def test_when_composite():
    params = {"cpus": 4}
    opts = ["spam", "baz"]
    expr = When.from_string(f"parameters='cpus>2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is True
    expr = When.from_string(f"parameters='cpus=2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is False
