# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""``path/to/test.ext::family.p1=v1.p2=v2`` test case selectors."""

import argparse
import json

import pytest

import canary
from _canary import app
from _canary.cli.run import ReadPathsFromFile
from _canary.core.rules import parse_case_selector
from _canary.scanpaths import case_selectors
from _canary.scanpaths import split_case_selector
from _canary.session.workspace import Workspace

FOO = """\
import sys
import canary
canary.directives.parameterize("a,b", [(1, 2), (3, 4), (5, 6)])
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""

BAR = """\
import sys
import canary
canary.directives.parameterize("x", [0.5, 1.5])
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""

POST = """\
import sys
import canary
canary.directives.depends_on("foo.a=1.b=2")
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


@pytest.fixture
def suite(tmp_path, monkeypatch):
    root = tmp_path / "suite"
    (root / "t").mkdir(parents=True)
    (root / "t" / "foo.pyt").write_text(FOO)
    (root / "t" / "bar.pyt").write_text(BAR)
    (root / "t" / "post.pyt").write_text(POST)
    monkeypatch.chdir(root)
    return root


def select(root, scanpaths):
    with canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.create_selection(tag=None, scanpaths=scanpaths)
    return sorted(spec.name for spec in specs)


def classify(items):
    builder = app.classify_pathspec(items)
    assert not builder.errors, builder.errors
    request = builder.finalize()
    assert request is not None
    return request.value


def test_split_case_selector():
    assert split_case_selector("t/foo.pyt") == ("t/foo.pyt", None)
    assert split_case_selector("t/foo.pyt::foo.a=1") == ("t/foo.pyt", "foo.a=1")
    assert split_case_selector("root:t/foo.pyt::foo") == ("root:t/foo.pyt", "foo")


def test_parse_case_selector():
    assert parse_case_selector("foo") == ("foo", {})
    assert parse_case_selector("foo.a=1.b=2") == ("foo", {"a": "1", "b": "2"})
    assert parse_case_selector("foo.x=0.5") == ("foo", {"x": "0.5"})
    assert parse_case_selector("my.fam.x=1.25.y=2") == ("my.fam", {"x": "1.25", "y": "2"})


def test_cli_selector_payload(suite):
    value = classify(["t/foo.pyt::foo.a=3.b=4"])
    assert value == {str(suite / "t"): ["foo.pyt::foo.a=3.b=4"]}


def test_cli_selects_named_cases(suite):
    value = classify(["t/foo.pyt::foo.b=4.a=3", "t/bar.pyt::bar.x=0.5"])
    assert select(suite, value) == ["bar.x=0.5", "foo.a=3.b=4"]


def test_explicit_root_with_selector(suite):
    (suite / "deep" / "sub").mkdir(parents=True)
    (suite / "deep" / "sub" / "foo.pyt").write_text(FOO)
    value = classify([f"{suite / 'deep'}:sub/foo.pyt::foo.a=3.b=4"])
    assert value == {str(suite / "deep"): ["sub/foo.pyt::foo.a=3.b=4"]}
    assert select(suite, value) == ["foo.a=3.b=4"]


def test_family_selector_selects_all_cases(suite):
    value = classify(["t/foo.pyt::foo"])
    assert select(suite, value) == ["foo.a=1.b=2", "foo.a=3.b=4", "foo.a=5.b=6"]


def test_partial_parameters_select_subset(suite):
    value = classify(["t/foo.pyt::foo.a=5"])
    assert select(suite, value) == ["foo.a=5.b=6"]


def test_plain_entry_overrides_selector(suite):
    value = classify(["t/foo.pyt", "t/foo.pyt::foo.a=1.b=2"])
    assert case_selectors(value) == {}
    assert select(suite, value) == ["foo.a=1.b=2", "foo.a=3.b=4", "foo.a=5.b=6"]


def test_selected_case_keeps_upstream_dependencies(suite):
    value = classify(["t/post.pyt::post", "t/foo.pyt::foo.a=3.b=4"])
    assert select(suite, value) == ["foo.a=1.b=2", "foo.a=3.b=4", "post"]


def test_unmatched_selector_is_an_error(suite):
    value = classify(["t/foo.pyt::foo.a=9"])
    with pytest.raises(ValueError, match="no matching test case"):
        select(suite, value)


def test_selector_on_directory_is_an_error(suite):
    builder = app.classify_pathspec(["t::foo"])
    assert any("require a file" in e for e in builder.errors)


def test_selector_on_missing_file_is_an_error(suite):
    builder = app.classify_pathspec(["t/nope.pyt::foo"])
    assert any("no such file" in e for e in builder.errors)


def test_testpaths_file_selectors(suite):
    data = {"testpaths": [{"root": "t", "paths": ["foo.pyt::foo.a=5.b=6", "bar.pyt::bar.x=1.5"]}]}
    (suite / "tp.json").write_text(json.dumps(data))
    args = argparse.Namespace()
    ReadPathsFromFile("", "f_pathspec")(None, args, str(suite / "tp.json"), option_string="-f")
    assert args.request.value == {str(suite / "t"): ["bar.pyt::bar.x=1.5", "foo.pyt::foo.a=5.b=6"]}
    assert select(suite, args.request.value) == ["bar.x=1.5", "foo.a=5.b=6"]


def test_testpaths_file_reports_bad_selector(suite):
    data = {"testpaths": [{"root": "t", "paths": ["nope.pyt::foo"]}]}
    (suite / "tp.json").write_text(json.dumps(data))
    with pytest.raises(argparse.ArgumentError, match="nope.pyt::foo"):
        ReadPathsFromFile("", "f_pathspec")(None, argparse.Namespace(), str(suite / "tp.json"))
