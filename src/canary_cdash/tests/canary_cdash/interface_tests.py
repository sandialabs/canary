# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_cdash.interface — pure utility functions and api_filters."""

import os
import xml.dom.minidom as dom

import pytest

from canary_cdash.interface import api_filters
from canary_cdash.interface import as_int
from canary_cdash.interface import compare_value
from canary_cdash.interface import comparison_from_code
from canary_cdash.interface import escapexml
from canary_cdash.interface import find_build_type
from canary_cdash.interface import get_text
from canary_cdash.interface import legacy_filters_match
from canary_cdash.interface import no_proxy
from canary_cdash.interface import normalize_cdash_status
from canary_cdash.interface import server
from canary_cdash.interface import urlescape

# ---------------------------------------------------------------------------
# api_filters
# ---------------------------------------------------------------------------


def test_api_filters_default_combine_mode():
    af = api_filters()
    assert af.combine_mode == "and"


def test_api_filters_explicit_or_mode():
    af = api_filters(combine_mode="or")
    assert af.combine_mode == "or"


def test_api_filters_bad_combine_mode():
    with pytest.raises(AssertionError):
        api_filters(combine_mode="xor")


def test_api_filters_add_and_len():
    af = api_filters()
    af.add(field="status", comparison="is", value="Failed")
    assert len(af) == 1


def test_api_filters_add_bad_comparison():
    af = api_filters()
    with pytest.raises(AssertionError):
        af.add(field="status", comparison="maybe", value="x")


def test_api_filters_asdict_single():
    af = api_filters()
    af.add(field="status", comparison="is", value="Failed")
    d = af.asdict()
    assert d["filtercount"] == "1"
    assert d["field1"] == "status"
    assert d["compare1"] == str(af.compmap["is"])
    assert d["value1"] == "Failed"
    assert d["comparison1"] == "is"
    assert "filtercombine" not in d  # only added for >1 filters


def test_api_filters_asdict_multiple_adds_combine():
    af = api_filters(combine_mode="or")
    af.add(field="status", comparison="is", value="Failed")
    af.add(field="details", comparison="contains", value="Timeout")
    d = af.asdict()
    assert d["filtercount"] == "2"
    assert d["filtercombine"] == "or"


def test_api_filters_iter():
    af = api_filters()
    af.add(field="a", comparison="equal", value="1")
    af.add(field="b", comparison="equal", value="2")
    fields = [f.field for f in af]
    assert fields == ["a", "b"]


# ---------------------------------------------------------------------------
# get_text
# ---------------------------------------------------------------------------


def test_get_text_extracts_text_node():
    doc = dom.parseString("<root><tag>hello world</tag></root>")
    el = doc.getElementsByTagName("tag")[0]
    assert get_text(el) == "hello world"


def test_get_text_strips_whitespace():
    doc = dom.parseString("<root><tag>  trimmed  </tag></root>")
    el = doc.getElementsByTagName("tag")[0]
    assert get_text(el) == "trimmed"


def test_get_text_empty_element():
    doc = dom.parseString("<root><tag></tag></root>")
    el = doc.getElementsByTagName("tag")[0]
    assert get_text(el) == ""


# ---------------------------------------------------------------------------
# escapexml / urlescape
# ---------------------------------------------------------------------------


def test_escapexml_ampersand():
    assert escapexml("a & b") == "a &amp; b"


def test_escapexml_angle_brackets():
    assert escapexml("<tag>") == "&lt;tag&gt;"


def test_escapexml_plain_text():
    assert escapexml("hello world") == "hello world"


def test_urlescape_spaces():
    assert urlescape("hello world") == "hello+world"


def test_urlescape_multiple_spaces():
    assert urlescape("a b c") == "a+b+c"


def test_urlescape_no_spaces():
    assert urlescape("nospaces") == "nospaces"


# ---------------------------------------------------------------------------
# no_proxy
# ---------------------------------------------------------------------------


def test_no_proxy_removes_vars(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://proxy:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    with no_proxy():
        assert "http_proxy" not in os.environ
        assert "HTTPS_PROXY" not in os.environ


def test_no_proxy_restores_vars(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://proxy:3128")
    with no_proxy():
        pass
    assert os.environ.get("http_proxy") == "http://proxy:3128"


def test_no_proxy_does_not_fail_when_vars_absent():
    # No exception when proxy vars are not set
    with no_proxy():
        pass


# ---------------------------------------------------------------------------
# normalize_cdash_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("passed", "Passed"),
        ("PASSED", "Passed"),
        ("failed", "Failed"),
        ("FAILED", "Failed"),
        ("not run", "Missing"),
        ("notrun", "Missing"),
        ("not_run", "Missing"),
        ("missing", "Missing"),
        ("MISSING", "Missing"),
        ("custom", "Custom"),  # falls through to title()
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_cdash_status(value, expected):
    assert normalize_cdash_status(value) == expected


# ---------------------------------------------------------------------------
# find_build_type
# ---------------------------------------------------------------------------


def test_find_build_type_cmake_type():
    c = {"command": "-DCMAKE_BUILD_TYPE=Release"}
    b = {"buildname": "foo"}
    assert find_build_type(c, b) == "Release"


def test_find_build_type_cmake_type_string():
    c = {"command": "-DCMAKE_BUILD_TYPE:STRING=Debug"}
    b = {"buildname": "foo"}
    assert find_build_type(c, b) == "Debug"


def test_find_build_type_cmake_type_with_space():
    c = {"command": "-D CMAKE_BUILD_TYPE=RelWithDebInfo"}
    b = {"buildname": "foo"}
    assert find_build_type(c, b) == "RelWithDebInfo"


def test_find_build_type_from_buildname_keyword():
    c = {"command": ""}
    b = {"buildname": "myproject build_type=MinSizeRel"}
    assert find_build_type(c, b) == "MinSizeRel"


def test_find_build_type_dbg_opt():
    assert find_build_type({}, {"buildname": "my dbg build"}) == "Debug"
    assert find_build_type({}, {"buildname": "my opt build"}) == "Release"


def test_find_build_type_nevada_path():
    assert find_build_type({}, {"buildname": "AlegraNevada/Release foo"}) == "Release"


def test_find_build_type_buildtype_key():
    assert find_build_type({}, {"buildname": "foo", "buildType": "MinSizeRel"}) == "MinSizeRel"


def test_find_build_type_default():
    assert find_build_type({}, {"buildname": "nothing matches here"}) == "RelWithDebInfo"


def test_find_build_type_non_dict_configure():
    # configure is not a dict → command = ""
    assert find_build_type(None, {"buildname": "foo"}) == "RelWithDebInfo"


# ---------------------------------------------------------------------------
# comparison_from_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, expected",
    [
        ("41", "equal"),
        ("42", "not equal"),
        ("43", "greater than"),
        ("44", "less than"),
        ("61", "is"),
        ("62", "is not"),
        ("63", "contains"),
        ("64", "does not contain"),
        ("65", "endswith"),
        ("99", "contains"),  # fallback
        (41, "equal"),  # int input via str()
    ],
)
def test_comparison_from_code(code, expected):
    assert comparison_from_code(code) == expected


# ---------------------------------------------------------------------------
# compare_value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actual, comparison, expected, result",
    [
        ("hello", "equal", "hello", True),
        ("hello", "equal", "world", False),
        ("hello", "is", "hello", True),
        ("hello", "not equal", "world", True),
        ("hello", "not equal", "hello", False),
        ("hello", "is not", "world", True),
        ("hello world", "contains", "world", True),
        ("hello world", "contains", "xyz", False),
        ("hello world", "does not contain", "xyz", True),
        ("hello world", "does not contain", "world", False),
        ("hello", "startswith", "hel", True),
        ("hello", "startswith", "world", False),
        ("hello", "endswith", "llo", True),
        ("hello", "endswith", "hel", False),
        ("10", "greater than", "5", True),
        ("3", "greater than", "5", False),
        ("3", "less than", "5", True),
        ("10", "less than", "5", False),
        ("abc", "greater than", "xyz", False),  # non-numeric → False
        ("abc", "less than", "xyz", False),
        ("hello", "EQUAL", "hello", True),  # case-insensitive comparison
        ("hello", "unknown_op", "hello", False),  # unknown → False
    ],
)
def test_compare_value(actual, comparison, expected, result):
    assert compare_value(actual, comparison, expected) == result


# ---------------------------------------------------------------------------
# legacy_filters_match
# ---------------------------------------------------------------------------


def test_legacy_filters_match_no_filters():
    assert legacy_filters_match({"status": "Failed"}, {}) is True
    assert legacy_filters_match({"status": "Failed"}, {"filtercount": 0}) is True


def test_legacy_filters_match_single_and():
    row = {"status": "Failed"}
    filters = {"filtercount": 1, "field1": "status", "comparison1": "is", "value1": "Failed"}
    assert legacy_filters_match(row, filters) is True


def test_legacy_filters_match_single_fails():
    row = {"status": "Passed"}
    filters = {"filtercount": 1, "field1": "status", "comparison1": "is", "value1": "Failed"}
    assert legacy_filters_match(row, filters) is False


def test_legacy_filters_match_and_mode_all_must_pass():
    row = {"status": "Failed", "details": "Timeout"}
    filters = {
        "filtercount": 2,
        "filtercombine": "and",
        "field1": "status",
        "comparison1": "is",
        "value1": "Failed",
        "field2": "details",
        "comparison2": "contains",
        "value2": "Timeout",
    }
    assert legacy_filters_match(row, filters) is True


def test_legacy_filters_match_and_mode_partial_fail():
    row = {"status": "Failed", "details": "Diffed"}
    filters = {
        "filtercount": 2,
        "filtercombine": "and",
        "field1": "status",
        "comparison1": "is",
        "value1": "Failed",
        "field2": "details",
        "comparison2": "contains",
        "value2": "Timeout",
    }
    assert legacy_filters_match(row, filters) is False


def test_legacy_filters_match_or_mode():
    row = {"status": "Passed", "details": "Timeout"}
    filters = {
        "filtercount": 2,
        "filtercombine": "or",
        "field1": "status",
        "comparison1": "is",
        "value1": "Failed",
        "field2": "details",
        "comparison2": "contains",
        "value2": "Timeout",
    }
    assert legacy_filters_match(row, filters) is True


def test_legacy_filters_match_uses_compare_code_when_no_comparison():
    row = {"status": "Failed"}
    # Use compare1 (numeric code) instead of comparison1 (string name)
    filters = {
        "filtercount": 1,
        "field1": "status",
        "compare1": "61",  # "is"
        "value1": "Failed",
    }
    assert legacy_filters_match(row, filters) is True


# ---------------------------------------------------------------------------
# as_int
# ---------------------------------------------------------------------------


def test_as_int_integer():
    assert as_int(42) == 42


def test_as_int_string_number():
    assert as_int("7") == 7


def test_as_int_non_numeric_string():
    assert as_int("foo") == "foo"


def test_as_int_none():
    assert as_int(None) == "None"


def test_as_int_float():
    assert as_int(3.9) == 3


# ---------------------------------------------------------------------------
# server.build_api_url
# ---------------------------------------------------------------------------


def test_server_build_api_url_no_query():
    s = server("http://cdash.example.com", "MyProject")
    url = s.build_api_url(path="index.php")
    assert url == "http://cdash.example.com/api/v1/index.php"


def test_server_build_api_url_with_query():
    s = server("http://cdash.example.com", "MyProject")
    url = s.build_api_url(path="index.php", query="project=MyProject")
    assert url == "http://cdash.example.com/api/v1/index.php?project=MyProject"


# ---------------------------------------------------------------------------
# server.normalize_index_build
# ---------------------------------------------------------------------------


def test_normalize_index_build_minimal():
    s = server("http://cdash.example.com", "MyProject")
    build = {"buildname": "mybuild", "site": "mysite"}
    group = {"name": "Nightly", "unixtimestamp": 12345}
    result = s.normalize_index_build(build, group)
    assert result["buildname"] == "mybuild"
    assert result["buildgroup"] == "Nightly"
    assert result["unixtimestamp"] == 12345
    assert result["site"] == "mysite"


def test_normalize_index_build_sets_has_flags():
    s = server("http://cdash.example.com", "MyProject")
    build = {"buildname": "b", "configure": {"command": "", "error": 0, "warning": 0}}
    group = {"name": "N", "unixtimestamp": 0}
    result = s.normalize_index_build(build, group)
    assert result["hasconfigure"] is True
    assert result["hastest"] is False


def test_normalize_index_build_aliases_hascompilation_hasbuild():
    s = server("http://cdash.example.com", "P")
    build = {"buildname": "b", "hascompilation": True}
    group = {"name": "N", "unixtimestamp": 0}
    result = s.normalize_index_build(build, group)
    assert result["hasbuild"] is True


def test_normalize_index_build_sets_build_type():
    s = server("http://cdash.example.com", "P")
    build = {"buildname": "b", "configure": {"command": "-DCMAKE_BUILD_TYPE=Debug"}}
    group = {"name": "N", "unixtimestamp": 0}
    result = s.normalize_index_build(build, group)
    assert result["build_type"] == "Debug"
