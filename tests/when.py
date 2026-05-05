# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import pytest

from _canary.when import InvalidSyntax
from _canary.when import When
from _canary.when import when as when_func


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


# Security test: ParameterExpression should block code execution via builtins
def test_parameterexpression_blocks_builtins():
    from _canary.expression import ParameterExpression

    # Try to access a builtin (should be blocked)
    expr = ParameterExpression("__import__('os').system('echo hacked')")
    # Should not execute, should raise SyntaxError or NameError or return False
    try:
        result = expr.evaluate({})
    except (SyntaxError, NameError):
        result = False
    assert result is False, "ParameterExpression should block access to builtins and code execution"
    # Try to access another builtin
    expr2 = ParameterExpression("open('somefile.txt', 'w')")
    try:
        result2 = expr2.evaluate({})
    except (SyntaxError, NameError):
        result2 = False
    assert result2 is False, "ParameterExpression should block open() and other builtins"


def test_when_composite():
    params = {"cpus": 4}
    opts = ["spam", "baz"]
    expr = When.from_string(f"parameters='cpus>2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is True
    expr = When.from_string(f"parameters='cpus=2' options='spam and baz' platforms={sys.platform}")
    assert expr.evaluate(parameters=params, on_options=opts).value is False


def test_factory_dict_equivalent_to_kwargs():
    w = When.factory({"options": "dbg", "testname": "foo"})
    assert w.option_expr == "dbg"
    assert w.testname_expr == "foo"
    assert w.platform_expr is None


def test_factory_string_uses_cache_identity():
    w1 = When.factory("options=dbg")
    w2 = When.factory("options=dbg")
    # When.from_string caches; repeated call should return same object
    assert w1 is w2


def test_factory_none_is_equivalent_not_identity():
    w1 = When.factory(None)
    w2 = When.factory(None)
    assert w1 is not w2
    assert w1.evaluate().value is True
    assert w2.evaluate().value is True


def test_from_string_strips_quotes_single_and_double():
    w = When.from_string("options='dbg' testname=\"foo\"")
    assert w.option_expr == "dbg"
    assert w.testname_expr == "foo"


def test_from_string_triple_quotes_are_stripped():
    w = When.from_string("options='''dbg'''")
    assert w.option_expr == "dbg"


def test_from_string_allows_newlines_tokens_are_skipped():
    # NEWLINE tokens are ignored by from_string loop
    w = When.from_string("options=dbg\n")
    assert w.option_expr == "dbg"


def test_from_string_allows_empty_value_tokenizes_as_newline():
    w = When.from_string("options=")
    assert w.option_expr is not None


def test_from_string_missing_equal_raises_syntaxerror():
    with pytest.raises(SyntaxError):
        When.from_string("options dbg")


def test_when_function_accepts_bool_passthrough():
    assert when_func(True) is True
    assert when_func(False) is False


def test_when_function_with_string_expression():
    assert when_func("options=dbg", on_options=["dbg"]) is True
    assert when_func("options=dbg", on_options=["other"]) is False


def test_when_function_with_dict_expression():
    assert when_func({"options": "dbg"}, on_options=["dbg"]) is True
    assert when_func({"options": "dbg"}, on_options=["other"]) is False


def test_safe_substitute_uppercase_keys_are_available_for_parameters():
    # When.evaluate() copies parameters into kwds and also adds uppercase variants.
    w = When.from_string("options='$OPT'")
    assert w.evaluate(on_options=["dbg"], parameters={"opt": "dbg"}).value is True
    assert w.evaluate(on_options=["dbg"], parameters={"opt": "fast"}).value is False


def test_testname_alias_name_in_from_string():
    w = When.from_string("name=foo")
    assert w.testname_expr == "foo"
    assert w.evaluate(testname="foo").value is True
    assert w.evaluate(testname="bar").value is False


def test_parameter_alias_parameter_in_from_string():
    w = When.from_string("parameter='a=1'")
    assert w.parameter_expr == "a=1"
    assert w.evaluate(parameters={"a": 1}).value is True
    assert w.evaluate(parameters={"a": 2}).value is False


def test_platform_expression_any_is_not_special_by_default():
    w = When.from_string("platform=any")
    assert w.platform_expr == "any"
    assert w.evaluate().value is False


def test_option_alias_option_in_from_string():
    w = When.from_string("option=dbg")
    assert w.option_expr == "dbg"
    assert w.evaluate(on_options=["dbg"]).value is True
    assert w.evaluate(on_options=["fast"]).value is False


def test_keywords_case_sensitivity_defaults_to_case_sensitive_false_in_reasoning():
    # AnyMatcher is created with case_sensitive=False for keywords
    w = When.from_string("keywords=FAST")
    assert w.evaluate(keywords=["fast"]).value is True
    assert w.evaluate(keywords=["FaSt"]).value is True
    assert w.evaluate(keywords=["slow"]).value is False


def test_options_case_sensitive_default_true():
    # OptionMatcher uses anymatch with default case_sensitive=True
    w = When.from_string("options=DBG")
    assert w.evaluate(on_options=["DBG"]).value is True
    assert w.evaluate(on_options=["dbg"]).value is False


def test_testname_case_sensitive_default_true():
    w = When.from_string("testname=Foo")
    assert w.evaluate(testname="Foo").value is True
    assert w.evaluate(testname="foo").value is False
