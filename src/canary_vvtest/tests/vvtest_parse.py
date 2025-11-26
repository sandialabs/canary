# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys

import _canary.util.filesystem as fs
import canary_vvtest.generator as generator
from _canary import workspace
from _canary.enums import list_parameter_space


def generate_specs(generators, on_options=None):
    from _canary import config

    specs = config.pluginmanager.hook.canary_generate(generators=generators, on_options=on_options)
    return specs


def test_parse_parameterize():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (autotype) : np,n = 1,2 3,4 5,6
# VVT: : 7,8
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "parameterize"
    assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
    names, values, kwds, _ = generator.p_PARAMETERIZE(commands[0])
    assert names == ["np", "n"]
    assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
    assert kwds == {"type": list_parameter_space}


def test_parse_autotype():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (autotype) : np,n = 1,2 3,4 5,6
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "parameterize"
    assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6"
    assert commands[0].options == [("autotype", True)]


def test_parse_parameterize_1():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (int, float) : np, mesh_factor = 1 , 1.0    1 , 0.5    1 , 0.25
"""
    args = list(generator.p_VVT(s))
    assert args[0].command == "parameterize"
    names, values, _, _ = generator.p_PARAMETERIZE(args[0])
    assert names == ["np", "mesh_factor"]
    assert values == [[1, 1.0], [1, 0.5], [1, 0.25]]


def test_parse_parameterize_types():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (str) : a, b = 1 , 1.0    1 , 0.5    1 , 0.25
# VVT: parameterize (int, float) : a, b = 1 , 1.0    1 , 0.5    1 , 0.25
# VVT: parameterize (autotype) : a, b = 1 , 1.0    1 , 0.5    1 , 0.25
"""
    args = list(generator.p_VVT(s))
    assert args[0].command == "parameterize"
    names, values, _, _ = generator.p_PARAMETERIZE(args[0])
    assert names == ["a", "b"]
    assert values == [["1", "1.0"], ["1", "0.5"], ["1", "0.25"]]
    assert args[1].command == "parameterize"
    names, values, _, _ = generator.p_PARAMETERIZE(args[1])
    assert names == ["a", "b"]
    assert values == [[1, 1.0], [1, 0.5], [1, 0.25]]
    assert args[2].command == "parameterize"
    names, values, _, _ = generator.p_PARAMETERIZE(args[2])
    assert names == ["a", "b"]
    assert values == [[1, 1.0], [1, 0.5], [1, 0.25]]


def test_csplit():
    assert generator.csplit("1 , 1.0    1 , 0.5    1 , 0.25") == [
        ["1", "1.0"],
        ["1", "0.5"],
        ["1", "0.25"],
    ]
    assert generator.csplit("1 , baz    1 , 'foo'    5.0 , 0.25") == [
        ["1", "baz"],
        ["1", "foo"],
        ["5.0", "0.25"],
    ]
    assert generator.csplit("spam , baz    \"eggs\" , 'foo'    wubble , 0.25") == [
        ["spam", "baz"],
        ["eggs", "foo"],
        ["wubble", "0.25"],
    ]


def test_parse_copy_rename():
    s = """\
#!/usr/bin/env python3
# VVT: copy (rename) : foo, baz  spam   ,ham
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "copy"
    assert commands[0].options == [("rename", True)]
    file_pairs = generator.csplit(commands[0].argument)
    assert file_pairs == [["foo", "baz"], ["spam", "ham"]]


def test_parse_baseline():
    s = """\
#!/usr/bin/env python3
# VVT: baseline : foo, baz  spam   ,ham
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "baseline"
    file_pairs = generator.csplit(commands[0].argument)
    assert file_pairs == [["foo", "baz"], ["spam", "ham"]]


def test_parse_link_rename():
    s = """\
#!/usr/bin/env python3
# VVT : link (rename) : 3DTmWave.g,3DTmWave.pregen.g
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "link"
    assert commands[0].options == [("rename", True)]
    file_pairs = generator.csplit(commands[0].argument)
    assert file_pairs == [["3DTmWave.g", "3DTmWave.pregen.g"]]


def test_parse_link_rename_1():
    s = """\
#!/usr/bin/env python3
# VVT : link (rename) : multiblock_rectangle_pml.exo, multiblock_rectangle_pml.prebuilt.exo
"""
    commands = list(generator.p_VVT(s))
    assert commands[0].command == "link"
    assert commands[0].options == [("rename", True)]
    file_pairs = generator.csplit(commands[0].argument)
    assert file_pairs == [["multiblock_rectangle_pml.exo", "multiblock_rectangle_pml.prebuilt.exo"]]


def test_parse_parameterize_gen(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT : parameterize (generator) : python3 my-script.py
"""
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("my-test.vvt", "w") as fh:
            fh.write(s)
        with open("my-script.py", "w") as fh:
            fh.write(
                """\
import json
a = [{'A': 1.0, 'B': 2.0}, {'B': 4.0, 'A': 3.0}]
print(json.dumps(a))
"""
            )
        command = next(generator.p_VVT(s))
        names, values, _, _ = generator.p_PARAMETERIZE(command)
    assert names == ["A", "B"]
    assert values == [[1.0, 2.0], [3.0, 4.0]]


def test_parse_parameterize_gen_deps(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT : parameterize (generator) : python3 my-script.py
"""
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("my-test.vvt", "w") as fh:
            fh.write(s)
        with open("my-script.py", "w") as fh:
            fh.write(
                """\
import json
a = [{'A': 1.0, 'B': 2.0}, {'B': 4.0, 'A': 3.0}]
print(json.dumps(a))
deps = [None, 'a.*']
print(json.dumps(deps))
"""
            )
        command = next(generator.p_VVT(s))
        names, values, _, deps = generator.p_PARAMETERIZE(command)
    assert names == ["A", "B"]
    assert values == [[1.0, 2.0], [3.0, 4.0]]
    assert deps == [None, "a.*"]


def test_parse_parameterize_gen_deps_2(tmpdir):
    # this is a more complicated example of dynamic parameter and dependency generation taken from
    # a customer.
    preload = os.path.join(tmpdir.strpath, "preload")
    fs.touchp(os.path.join(preload, "my-env.sh"))
    fs.touchp(os.path.join(preload, "spam-env.sh"))
    fs.touchp(os.path.join(preload, "eggs-env.sh"))
    fs.touchp(os.path.join(preload, "baz-env.sh"))
    source = os.path.join(tmpdir.strpath, "source")
    fs.mkdirp(source)
    regression = os.path.join(tmpdir.strpath, "regression")
    fs.mkdirp(regression)
    testdir = os.path.join(tmpdir.strpath, "X/Y/Z")
    fs.mkdirp(testdir)
    with fs.working_dir(testdir):
        with open("my-test.vvt", "w") as fh:
            fh.write(
                """\
#!/usr/bin/env python3
# VVT: keywords: small
# VVT: link: ../../../preload
# VVT: parameterize (generator,testname = "create_inputs"):  vvtest_param_generator.py create_inputs
# VVT: parameterize (generator,testname = "spam"):  vvtest_param_generator.py spam
# VVT: parameterize (generator,testname = "ham"):  vvtest_param_generator.py ham
# VVT: parameterize (generator,testname = "eggs"):  vvtest_param_generator.py eggs
# VVT: parameterize (generator,testname = "baz"):  vvtest_param_generator.py baz
# VVT: parameterize (generator,testname = "bacon"):  vvtest_param_generator.py bacon

# VVT: name : create_inputs
# VVT: preload (testname="create_inputs") : source-script preload/my-env.sh
# VVT: link (testname="create_inputs") : ../../../source ../../../cables
# VVT: timeout (testname="create_inputs") : 5m
# VVT: parameterize (testname="create_inputs") : np =1
#
# VVT: name : spam
# VVT: preload (testname="spam") : source-script preload/spam-env.sh
# VVT: timeout (testname="spam") : 5m
#
# VVT: name : ham
# VVT: link (testname="ham") : ../../../cables
# VVT: preload (testname="ham") : source-script preload/my-env.sh
# VVT: timeout (testname="ham") : 5m
#
# VVT: name : eggs
# VVT: preload (testname="eggs") : source-script preload/eggs-env.sh
# VVT: timeout (testname="eggs") : 5m
#
# VVT: name : baz
# VVT: preload (testname="baz") : source-script preload/baz-env.sh
# VVT: timeout (testname="baz") : 3h
#
# One run uses the CCE's tools, the other is EMPIRE-only using a pregen file..
# VVT: name : bacon
# VVT: preload (testname="bacon") : source-script preload/my-env.sh
# VVT: timeout (testname="bacon") : 15m
# VVT: link (testname="bacon"): ../../../cables ../../../source ../../../regression

import sys
import vvtest_util as vvt

if __name__ == "__main__":
    assert 0, "This test is not actually run"
"""
            )
        with open("vvtest_param_generator.py", "w") as fh:
            fh.write(f"#!{sys.executable}\n")
            fh.write("import json\nimport sys\n")
            fh.write("step = sys.argv[1]\n")
            fh.write("if step == 'create_inputs':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 1, 'b': 'B'}]))\n")
            fh.write("elif step == 'spam':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 1, 'b': 'B'}]))\n")
            fh.write("    print(json.dumps([{'create_inputs': {'a': 'A', 'np': 1, 'b': 'B'}}]))\n")
            fh.write("elif step == 'ham':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 1}]))\n")
            fh.write("elif step == 'eggs':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 1, 'b': 'B', 'target_np': 12}]))\n")
            fh.write(
                "    print(json.dumps([{'create_inputs': {'a': 'A', 'np': 1, 'b': 'B'}, 'ham': {'a': 'A', 'np': 1}}]))\n"
            )
            fh.write("elif step == 'baz':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 12, 'b': 'B'}]))\n")
            fh.write(
                "    print(json.dumps([{'create_inputs': {'a': 'A', 'np': 1, 'b': 'B'}, 'spam': {'a': 'A', 'np': 1, 'b': 'B'}, 'ham': {'a': 'A', 'np': 1}, 'eggs': {'a': 'A', 'np': 1, 'b': 'B', 'target_np': 12}}]))\n"
            )
            fh.write("elif step == 'bacon':\n")
            fh.write("    print(json.dumps([{'a': 'A', 'np': 12, 'b': 'B'}]))\n")
            fh.write(
                "    print(json.dumps([{'create_inputs': {'a': 'A', 'np': 1, 'b': 'B'}, 'baz': {'a': 'A', 'np': 12, 'b': 'B'}}]))\n"
            )
            fh.write("else:\n    assert 0\n")
        fs.set_executable("vvtest_param_generator.py")
    with fs.working_dir(tmpdir.strpath):
        generators = workspace.find_generators_in_path(".")
        specs = generate_specs(generators)
        assert len(specs) == 6
        assert specs[0].name == "create_inputs.a=A.b=B.np=1"
        for spec in specs[1:]:
            dep_names = [_.name for _ in spec.dependencies]
            if spec.name == "spam.a=A.b=B.np=1":
                assert spec.dependencies[0] == specs[0]
            elif spec.name == "ham.a=A.np=1":
                assert len(spec.dependencies) == 0
            elif spec.name == "eggs.a=A.b=B.np=1.target_np=12":
                assert len(spec.dependencies) == 2
                assert specs[0] in spec.dependencies
                assert "ham.a=A.np=1" in dep_names
            elif spec.name == "baz.a=A.b=B.np=12":
                assert len(spec.dependencies) == 4
                assert specs[0] in spec.dependencies
                assert "spam.a=A.b=B.np=1" in dep_names
                assert "ham.a=A.np=1" in dep_names
                assert "eggs.a=A.b=B.np=1.target_np=12" in dep_names
            elif spec.name == "bacon.a=A.b=B.np=12":
                assert len(spec.dependencies) == 2
                assert "baz.a=A.b=B.np=12" in dep_names
            else:
                assert 0, f"Unknown spec {spec.name}"


def test_make_table():
    table = generator.make_table("a.0,'b,0',c, 1-0   e ,2.0  ,    6.5,       a.b-foo-baz")
    assert table == [["a.0", "'b,0'", "c", "1-0"], ["e", "2.0", "6.5", "a.b-foo-baz"]], table
    table = generator.make_table("1,2 3,4 5,6 7,8")
    assert table == [["1", "2"], ["3", "4"], ["5", "6"], ["7", "8"]]
