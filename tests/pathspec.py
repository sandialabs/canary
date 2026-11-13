# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

import pytest

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


def _write_testpaths(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def test_testpaths_file_reports_every_missing_path(tmp_path):
    from _canary.scanpaths import TestPathsFileError
    from _canary.scanpaths import read_testpaths_file

    touchp(str(tmp_path / "tests" / "a.pyt"))
    file = _write_testpaths(
        tmp_path / "x_testpaths.json",
        {
            "testpaths": [
                {"root": "tests", "paths": ["a.pyt", "gone.pyt", "sub/*.vvt"]},
                {"root": "no-such-root", "paths": ["b.pyt"]},
            ]
        },
    )
    with pytest.raises(TestPathsFileError) as excinfo:
        read_testpaths_file(file)
    message = str(excinfo.value)
    assert "3 problems" in message
    assert "tests/gone.pyt: no such file or directory" in message
    assert "tests/sub/*.vvt: no paths matched pattern" in message
    assert "root 'no-such-root' does not exist" in message
    assert "a.pyt" not in message.replace("gone.pyt", "")


def test_testpaths_file_resolves_relative_to_file_and_accepts_description(tmp_path):
    from _canary.scanpaths import read_testpaths_file

    touchp(str(tmp_path / "tests" / "a.pyt"))
    touchp(str(tmp_path / "tests" / "sub" / "b.pyt"))
    file = _write_testpaths(
        tmp_path / "x_testpaths.json",
        {
            "description": "derived by grepping for model FOO",
            "testpaths": [{"root": "tests", "paths": ["a.pyt", "sub/*.pyt"]}],
        },
    )
    with working_dir(str(tmp_path.parent)):
        paths = read_testpaths_file(file)
    assert paths == {str(tmp_path / "tests"): ["a.pyt", os.path.join("sub", "b.pyt")]}


@pytest.mark.parametrize(
    "content, expected",
    [
        ("{bad", "invalid JSON"),
        (
            json.dumps({"testpaths": [{"root": "tests", "paths": "a.pyt"}]}),
            "does not match the testpaths schema",
        ),
    ],
)
def test_testpaths_file_reports_malformed_file(tmp_path, content, expected):
    from _canary.scanpaths import TestPathsFileError
    from _canary.scanpaths import read_testpaths_file

    file = tmp_path / "x_testpaths.json"
    file.write_text(content)
    with pytest.raises(TestPathsFileError, match=expected):
        read_testpaths_file(str(file))


def test_testpaths_file_reports_unreadable_file(tmp_path):
    from _canary.scanpaths import TestPathsFileError
    from _canary.scanpaths import read_testpaths_file

    with pytest.raises(TestPathsFileError, match="cannot read testpaths file"):
        read_testpaths_file(str(tmp_path / "missing.json"))


def test_run_dash_f_rejects_missing_paths_with_message(tmp_path):
    """``canary run -f`` surfaces the missing entries as an argparse error."""
    file = _write_testpaths(
        tmp_path / "x_testpaths.json", {"testpaths": [{"root": ".", "paths": ["gone.pyt"]}]}
    )
    action = ReadPathsFromFile(["-f"], "f_pathspec")
    with pytest.raises(argparse.ArgumentError, match="gone.pyt: no such file or directory"):
        action(None, argparse.Namespace(), file, option_string="-f")


def test_collect_dash_f_rejects_missing_paths_with_message(tmp_path):
    """``canary find/collect -f`` shows the message instead of 'invalid ... value'."""
    from _canary.generation.collect import read_recursedirs

    file = _write_testpaths(
        tmp_path / "x_testpaths.json", {"testpaths": [{"root": ".", "paths": ["gone.pyt"]}]}
    )
    with pytest.raises(argparse.ArgumentTypeError, match="gone.pyt: no such file or directory"):
        read_recursedirs(file)


def test_collector_reports_once_per_root_and_does_not_search_listed_files(tmp_path, monkeypatch):
    """Files listed under a root are taken as given, with one progress line per root."""
    from _canary.generation import collect as collect_mod
    from _canary.generation.collect import Collector

    touchp(str(tmp_path / "a" / "single" / "file.pyt"))
    touchp(str(tmp_path / "a" / "single" / "sibling.pyt"))  # same dir, not listed
    touchp(str(tmp_path / "another" / "file.pyt"))
    touchp(str(tmp_path / "dir" / "deep" / "x.pyt"))

    messages: list[str] = []
    real = collect_mod.logger.progress_monitor

    def spy(message, *args, **kwargs):
        messages.append(message)
        return real(message, *args, **kwargs)

    monkeypatch.setattr(collect_mod.logger, "progress_monitor", spy)
    monkeypatch.setattr(Collector, "matches", lambda self, name: name.endswith(".pyt"))
    collector = Collector()
    collector.collect_from_root(str(tmp_path), ["a/single/file.pyt", "another/file.pyt", "dir"])

    assert sorted(collector.files[str(tmp_path)]) == sorted(
        [
            os.path.join("a", "single", "file.pyt"),
            os.path.join("another", "file.pyt"),
            os.path.join("dir", "deep", "x.pyt"),
        ]
    )
    collecting = [m for m in messages if "Collecting" in m]
    assert len(collecting) == 1
    assert collecting[0].endswith(f"generator files in {tmp_path}")


@pytest.mark.parametrize("entry_paths", ["missing", None, []])
def test_testpaths_entry_without_paths_scans_root(tmp_path, entry_paths):
    from _canary.scanpaths import read_testpaths_file

    touchp(str(tmp_path / "tests" / "a.pyt"))
    entry: dict = {"root": "tests"}
    if entry_paths != "missing":
        entry["paths"] = entry_paths
    file = _write_testpaths(tmp_path / "x_testpaths.json", {"testpaths": [entry]})
    assert read_testpaths_file(file) == {str(tmp_path / "tests"): []}


def test_testpaths_yaml_entry_with_root_only(tmp_path):
    from _canary.scanpaths import read_testpaths_file

    touchp(str(tmp_path / "tests" / "a.pyt"))
    file = tmp_path / "x_testpaths.yaml"
    file.write_text("testpaths:\n  - root: tests\n  - root: tests\n    paths:\n")
    assert read_testpaths_file(str(file)) == {str(tmp_path / "tests"): []}
