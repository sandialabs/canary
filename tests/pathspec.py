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
        args = argparse.Namespace(f_pathspec="./foo.json", on_options=[])
        args.pathspec = [
            "./baz",
            "+baz",
            "./spam",
            "./eggs:f.pyt",
            "./ham/f.pyt",
        ]
        ps.PathSpec.parse(args)
        assert args.paths == {
            os.getcwd(): ["bacon"],
            "./baz": [],
            "./spam": [],
            "./eggs": ["f.pyt"],
            f"{os.getcwd()}/ham": ["f.pyt"],
        }
        assert args.on_options == ["baz"]
