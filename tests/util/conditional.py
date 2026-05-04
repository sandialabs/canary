from _canary.util.conditional import Conditional


def test_matches_default_true():
    c = Conditional.make("x")
    assert c.matches()
    assert c.matches(family="foo", on_options=["dbg"], parameters={"a": 1}, keywords=["fast"])


def test_matches_family_via_dict_when():
    c = Conditional.make("x", when={"testname": "foo"})
    assert c.matches(family="foo")
    assert not c.matches(family="bar")
    assert not c.matches(family=None)


def test_matches_family_via_string_when_and_wildcards():
    c = Conditional.make("x", when="testname='foo*'")
    assert c.matches(family="foo")
    assert c.matches(family="foobar")
    assert not c.matches(family="bar")


def test_matches_options_simple():
    c = Conditional.make("x", when={"options": "dbg"})
    assert c.matches(on_options=["dbg"])
    assert not c.matches(on_options=["opt"])
    assert not c.matches(on_options=None)


def test_matches_options_boolean_logic():
    c = Conditional.make("x", when="options='dbg and not fast'")
    assert c.matches(on_options=["dbg"])
    assert not c.matches(on_options=["dbg", "fast"])


def test_matches_keywords_expression_case_insensitive():
    c = Conditional.make("x", when="keywords='fast and regression'")
    assert c.matches(keywords=["FAST", "Regression"])
    assert not c.matches(keywords=["fast"])
    assert not c.matches(keywords=None)


def test_matches_parameters_numeric_comparison():
    c = Conditional.make("x", when="parameters='a>1'")
    assert c.matches(parameters={"a": 2})
    assert not c.matches(parameters={"a": 1})
    assert not c.matches(parameters={"a": 0})
    assert not c.matches(parameters=None)


def test_matches_parameters_equality_string_form():
    # Adjust if ParameterExpression grammar differs in your codebase
    c = Conditional.make("x", when="parameters='mode=fast'")
    assert c.matches(parameters={"mode": "fast"})
    assert not c.matches(parameters={"mode": "slow"})


def test_matches_substitution_uses_parameters_and_uppercase_variants():
    # When.evaluate() adds uppercase variants of provided parameters
    c = Conditional.make("x", when="options='$OPT'")
    assert c.matches(on_options=["dbg"], parameters={"opt": "dbg"})
    assert not c.matches(on_options=["dbg"], parameters={"opt": "fast"})


def test_when_aliases_are_supported_in_string_form():
    # when.py supports: option->options, platform->platforms, parameter->parameters, name->testname
    c1 = Conditional.make("x", when="option=dbg")
    assert c1.matches(on_options=["dbg"])
    assert not c1.matches(on_options=["fast"])

    c2 = Conditional.make("x", when="parameter='a>1'")
    assert c2.matches(parameters={"a": 2})
    assert not c2.matches(parameters={"a": 1})

    c3 = Conditional.make("x", when="name=foo")
    assert c3.matches(family="foo")
    assert not c3.matches(family="bar")


def test_when_compiled_cached_for_identical_string():
    # When.from_string caches by input string; Conditional.make should reuse it
    c1 = Conditional.make("x", when="options=dbg")
    c2 = Conditional.make("y", when="options=dbg")
    assert c1.when is c2.when
