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
        p(None, args, "foo.json")
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
