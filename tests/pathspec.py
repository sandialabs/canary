# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

import _canary.plugins.subcommands.common.pathspec as ps
from _canary.util.filesystem import touchp
from _canary.util.filesystem import working_dir


def test_pathspec_setdefault():
    obj = type("a", (), {})
    x = ps.setdefault(obj, "foo", [])
    x.append("a")
    y = ps.setdefault(obj, "foo", [])
    assert y == ["a"]


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
        values = [
            "./baz",
            "+baz",
            "./spam",
            "./eggs:f.pyt",
            "./ham/f.pyt",
            "~bacon",
            "--",
            "--foo",
            "--bar",
        ]
        p = ps.PathSpec("", "f_pathspec")
        args = argparse.Namespace()
        p(None, args, "foo.json", option_string="-f")
        p = ps.PathSpec("", "pathspec")
        p(None, args, values)
        assert args.paths == {
            os.getcwd(): ["bacon"],
            "./baz": [],
            "./spam": [],
            "./eggs": ["f.pyt"],
            f"{os.getcwd()}/ham": ["f.pyt"],
        }
        assert args.on_options == ["baz"]
        assert args.off_options == ["bacon"]
        assert args.script_args == ["--foo", "--bar"]


def test_run_from_file(tmpdir):
    from _canary.util.testing import CanaryCommand

    with working_dir(tmpdir.strpath, create=True):
        touchp("tests/regression/2D/test_1.pyt")
        touchp("tests/regression/2D/test_2.pyt")
        touchp("tests/verification/2D/test_1.pyt")
        touchp("tests/verification/2D/test_2.pyt")
        touchp("tests/verification/3D/test_1.pyt")
        touchp("tests/verification/3D/test_2.pyt")
        touchp("tests/prototype/a/test_1.pyt")
        touchp("tests/prototype/a/test_2.pyt")
        touchp("tests/prototype/b/test_1.pyt")
        touchp("tests/prototype/b/test_2.pyt")
        data = {
            "root": "tests",
            "paths": [
                "regression/2D/test_1.pyt",
                "verification/2D/test_1.pyt",
                "verification/3D/test_1.pyt",
                "prototype/a/test_1.pyt",
                "prototype/b/test_1.pyt",
            ],
        }
        file = os.path.join(os.getcwd(), "file.json")
        with open(file, "w") as fh:
            json.dump({"testpaths": [data]}, fh, indent=2)
        command = CanaryCommand("run")
        assert os.path.exists(file)
        command("-f", file)
        assert os.path.exists("TestResults/regression/2D/test_1")
        assert os.path.exists("TestResults/verification/2D/test_1")
        assert os.path.exists("TestResults/verification/3D/test_1")
        assert os.path.exists("TestResults/prototype/a/test_1")
        assert os.path.exists("TestResults/prototype/b/test_1")

        assert not os.path.exists("TestResults/regression/2D/test_2")
        assert not os.path.exists("TestResults/verification/2D/test_2")
        assert not os.path.exists("TestResults/verification/3D/test_2")
        assert not os.path.exists("TestResults/prototype/a/test_2")
        assert not os.path.exists("TestResults/prototype/b/test_2")
