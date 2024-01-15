import sys

import pytest
from _nvtest.directives.when import InvalidSyntax
from _nvtest.directives.when import When


def test_when_sentinel():
    expr = When(True)
    assert expr.evaluate().value is True
    expr = When(None)
    assert expr.evaluate().value is True
    expr = When(False)
    assert expr.evaluate().value is False
    assert expr.evaluate().reason == "when=False"

    with pytest.raises(ValueError):
        expr = When([])


def test_when_platform():
    expr = When(f"platform={sys.platform}")
    assert expr.evaluate().value is True
    expr = When(f"platform='not {sys.platform}'")
    assert expr.evaluate().value is False

    with pytest.raises((InvalidSyntax, IndexError)):
        expr = When("platform='linux")
        expr.evaluate()


def test_when_name():
    expr = When("name=spam")
    assert expr.evaluate().value is False
    assert expr.evaluate(testname="spam").value is True


def test_when_options():
    expr = When("options='spam'")
    assert expr.evaluate(on_options=["spam"]).value is True
    assert expr.evaluate().value is False

    expr = When("options='spam and baz'")
    assert expr.evaluate(on_options=["spam", "baz"]).value is True
    assert expr.evaluate().value is False
    assert expr.evaluate(on_options=["spam"]).value is False
    assert expr.evaluate(on_options=["baz"]).value is False

    expr = When("options='spam or baz'")
    assert expr.evaluate(on_options=["spam", "baz"]).value is True
    assert expr.evaluate().value is False
    assert expr.evaluate(on_options=["spam"]).value is True
    assert expr.evaluate(on_options=["baz"]).value is True


def test_when_parameters():
    expr = When("parameters='np<4'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"np": 1}).value is True
    assert expr.evaluate(parameters={"np": 5}).value is False

    expr = When("parameters='np> 2 and np<6'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"np": 3}).value is True
    assert expr.evaluate(parameters={"np": 7}).value is False

    expr = When("parameters='!np'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"spam": "baz"}).value is True

    expr = When("parameters='np>2 and baz=spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"np": 3}).value is False
    assert expr.evaluate(parameters={"np": 3, "baz": "wubble"}).value is False
    assert expr.evaluate(parameters={"np": 3, "baz": "spam"}).value is True

    expr = When("parameters='np>2 or baz=spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"np": 3}).value is True
    assert expr.evaluate(parameters={"np": 3, "baz": "wubble"}).value is True
    assert expr.evaluate(parameters={"np": 3, "baz": "spam"}).value is True

    expr = When("parameters='np>2 or baz==spam'")
    assert expr.evaluate().value is False
    assert expr.evaluate(parameters={"np": 3}).value is True
    assert expr.evaluate(parameters={"np": 3, "baz": "wubble"}).value is True
    assert expr.evaluate(parameters={"np": 3, "baz": "spam"}).value is True


def test_when_composite():
    params = {"np": 4}
    opts = ["spam", "baz"]
    expr = When(f"parameters='np>2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is True
    expr = When(f"parameters='np=2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is False
