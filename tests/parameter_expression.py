# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.core.expression import ParameterExpression


def test_string_valued_comparison_is_non_match_not_exception() -> None:
    expr = ParameterExpression("np>2")
    assert expr.evaluate({"np": "abc"}) is False


def test_compiler_like_token_is_treated_as_non_match() -> None:
    expr = ParameterExpression("compiler=gcc-12")
    assert expr.evaluate({"compiler": "gcc-12"}) is False


def test_invalid_bang_expression_is_non_match() -> None:
    expr = ParameterExpression("!3")
    assert expr.evaluate({}) is False


def test_invalid_missing_name_after_wildcard_is_non_match() -> None:
    expr = ParameterExpression("P(*)")
    assert expr.evaluate({}) is False


def test_exponentiation_is_rejected_as_non_match() -> None:
    expr = ParameterExpression("np=9**9**9")
    assert expr.evaluate({"np": 9}) is False
