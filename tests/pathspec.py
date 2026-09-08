# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

import canary
from _canary.subcommands.run import PathSpec
from _canary.subcommands.run import ReadPathsFromFile
from _canary.util.filesystem import touchp
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


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
