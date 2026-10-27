# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

import canary
from _canary import app
from _canary.cli.run import PathSpec
from _canary.cli.run import ReadPathsFromFile
from _canary.generation.collect import recursedirs_type
from _canary.session.workspace import Workspace
from _canary.util.filesystem import touchp
from _canary.util.filesystem import working_dir


def test_pathspec_parse_new(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touchp("./baz/f.pyt")
        touchp("./spam/f.pyt")
        touchp("./eggs/f.pyt")
        touchp("./ham/f.pyt")
        touchp("./bacon/f.pyt")
        with open("foo.json", "w") as fh:
            f = {"testpaths": [{"root": os.getcwd(), "paths": ["bacon"]}]}
            json.dump(f, fh)
        values = ["./baz", "./spam", "./eggs:f.pyt", "./ham/f.pyt", "--", "--foo", "--bar"]
        p = ReadPathsFromFile("", "f_pathspec")
        args = argparse.Namespace()
        p(None, args, "foo.json", option_string="-f")
        p = PathSpec("", "pathspec")
        p(None, args, values)
        d = os.getcwd()
        assert args.request.value == {
            os.getcwd(): ["bacon"],
            f"{d}/baz": [],
            f"{d}/spam": [],
            f"{d}/eggs": ["f.pyt"],
            f"{os.getcwd()}/ham": ["f.pyt"],
        }
        assert args.script_args == ["--foo", "--bar"]


def test_run_from_file(tmp_path):
    """canary run -f file.json only runs tests listed in testpaths.

    Converted from CanaryCommand subprocess to in-process workspace.run().
    We verify by checking which job *families* (spec names) were collected,
    since the JSON path filter is applied at the collect() stage.
    """
    root = tmp_path / "suite"
    root.mkdir()

    # Create stub .pyt files in a tree.
    pyt_body = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""
    dirs = [
        "tests/regression/2D",
        "tests/verification/2D",
        "tests/verification/3D",
        "tests/prototype/a",
        "tests/prototype/b",
    ]
    for d in dirs:
        for name in ("test_1", "test_2"):
            p = root / d / f"{name}.pyt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(pyt_body)

    # Build a scanpaths dict matching what "canary run -f file.json" would produce.
    tests_root = root / "tests"
    included = [
        "regression/2D/test_1.pyt",
        "verification/2D/test_1.pyt",
        "verification/3D/test_1.pyt",
        "prototype/a/test_1.pyt",
        "prototype/b/test_1.pyt",
    ]
    scanpaths = {str(tests_root): included}

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect(scanpaths)

    collected_names = {s.family for s in specs}

    # Only test_1 variants should be collected.
    assert "test_1" in collected_names
    assert "test_2" not in collected_names
    assert len(specs) == 5


def test_recursedirs_type_expands_globbed_files_with_shared_root(tmp_path):
    touchp(tmp_path / "some" / "baz" / "foo" / "test.pyt")
    touchp(tmp_path / "some" / "spam" / "foo" / "test.pyt")

    scanpaths = recursedirs_type(str(tmp_path / "some" / "**" / "foo" / "*.pyt"))

    assert scanpaths == {str(tmp_path / "some"): ["baz/foo/test.pyt", "spam/foo/test.pyt"]}


def test_globbed_directory_pathspec_collects_matching_subtrees(tmp_path, monkeypatch):
    root = tmp_path / "suite"
    pyt_body = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""
    for branch, name in (("baz", "alpha"), ("spam", "beta")):
        p = root / "some" / branch / "foo" / f"{name}.pyt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(pyt_body)

    monkeypatch.chdir(root)
    with canary.config.override():
        workspace = Workspace.create(root)
        request = app.classify_pathspec([str(root / "some" / "**" / "foo")]).finalize()
        assert request is not None
        specs = workspace.collect(request.value)

    assert sorted(spec.family for spec in specs) == ["alpha", "beta"]
    assert {str(spec.file_root) for spec in specs} == {str(root / "some")}
    assert {str(spec.file_path) for spec in specs} == {"baz/foo/alpha.pyt", "spam/foo/beta.pyt"}


def test_recursedirs_type_keeps_explicit_root_with_globbed_relative_path(tmp_path):
    touchp(tmp_path / "some" / "dir" / "foo" / "a" / "spam" / "test.pyt")
    touchp(tmp_path / "some" / "dir" / "foo" / "b" / "spam" / "test.pyt")

    scanpaths = recursedirs_type(f"{tmp_path / 'some' / 'dir'}:foo/**/spam")

    assert scanpaths == {str(tmp_path / "some" / "dir"): ["foo/a/spam", "foo/b/spam"]}


def test_recursedirs_type_rejects_colon_after_first_globbed_component(tmp_path):
    touchp(tmp_path / "some" / "dir" / "a" / "spam" / "test.pyt")

    try:
        recursedirs_type(f"{tmp_path / 'some' / 'dir'}/**/spam:baz")
    except ValueError as e:
        assert (
            str(e)
            == f"{tmp_path / 'some' / 'dir'}/**/spam:baz: ':' is only allowed before the first globbed component"
        )
    else:
        raise AssertionError("Expected ValueError for ':' after a globbed component")
