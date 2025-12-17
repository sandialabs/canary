# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os

from _canary.plugins.subcommands.run import PathSpec
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
        values = [
            "./baz",
            "./spam",
            "./eggs:f.pyt",
            "./ham/f.pyt",
            "--",
            "--foo",
            "--bar",
        ]
        p = PathSpec("", "f_pathspec")
        args = argparse.Namespace()
        p(None, args, "foo.json", option_string="-f")
        p = PathSpec("", "pathspec")
        p(None, args, values)
        d = os.getcwd()
        assert args.scanpaths == {
            os.getcwd(): ["bacon"],
            f"{d}/baz": [],
            f"{d}/spam": [],
            f"{d}/eggs": ["f.pyt"],
            f"{os.getcwd()}/ham": ["f.pyt"],
        }
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
