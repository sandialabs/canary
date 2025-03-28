# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from typing import Any

import pytest

import _canary.plugins.generators.ctest as ctg
from _canary.util.filesystem import force_remove
from _canary.util.filesystem import which


@pytest.fixture(scope="module")
def loadtestfile():
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    tests = ctg.load(file)
    yield tests
    force_remove(os.path.join(os.path.dirname(__file__), "Testing"))


def test_parse_np():
    assert ctg.parse_np(["-n", "97"]) == 97
    assert ctg.parse_np(["-np", "23"]) == 23
    assert ctg.parse_np(["-c", "54"]) == 54
    assert ctg.parse_np(["--np", "82"]) == 82
    assert ctg.parse_np(["-n765"]) == 765
    assert ctg.parse_np(["-np512"]) == 512
    assert ctg.parse_np(["-c404"]) == 404
    assert ctg.parse_np(["--np=45"]) == 45
    assert ctg.parse_np(["--some-arg=4", "--other=foo"]) == 1


def find_property(properties: list[dict], name: str) -> Any:
    for prop in properties:
        if prop["name"] == name:
            return prop["value"]
    raise KeyError(name)


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile(loadtestfile):
    assert isinstance(loadtestfile, dict)


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_attached_files(loadtestfile):
    test = loadtestfile["attached_files"]
    assert find_property(test["properties"], "ATTACHED_FILES") == ["foo.txt", "bar.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_attached_files_on_fail(loadtestfile):
    test = loadtestfile["attached_files_on_fail"]
    assert find_property(test["properties"], "ATTACHED_FILES_ON_FAIL") == ["foo.txt", "bar.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_cost(loadtestfile):
    test = loadtestfile["cost"]
    assert find_property(test["properties"], "COST") == 1.0


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_depends(loadtestfile):
    test = loadtestfile["depends"]
    assert find_property(test["properties"], "DEPENDS") == ["attached_files", "cost"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_environment(loadtestfile):
    test = loadtestfile["environment"]
    environment = find_property(test["properties"], "ENVIRONMENT")
    assert environment == ["SPAM=1", "BAZ=2"]
    env = ctg.parse_environment(environment)
    assert env == {"SPAM": "1", "BAZ": "2"}


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_environment_modification(loadtestfile):
    test = loadtestfile["environment_modification"]
    environment_modification = find_property(test["properties"], "ENVIRONMENT_MODIFICATION")
    assert environment_modification == [
        "set=set:set",
        "unset=unset:unset",
        "string_append=string_append:string_append",
        "string_prepend=string_prepend:string_prepend",
        "path_list_append=path_list_append:path_list_append",
        "path_list_prepend=path_list_prepend:path_list_prepend",
        "cmake_list_append=cmake_list_append:cmake_list_append",
        "cmake_list_prepend=cmake_list_prepend:cmake_list_prepend",
    ]
    env = ctg.parse_environment_modification(environment_modification)
    print(env)
    assert env == [
        {"name": "set", "op": "set", "value": "set"},
        {"name": "unset", "op": "unset", "value": "unset"},
        {"name": "string_append", "op": "string_append", "value": "string_append"},
        {"name": "string_prepend", "op": "string_prepend", "value": "string_prepend"},
        {"name": "path_list_append", "op": "path_list_append", "value": "path_list_append"},
        {"name": "path_list_prepend", "op": "path_list_prepend", "value": "path_list_prepend"},
        {"name": "cmake_list_append", "op": "cmake_list_append", "value": "cmake_list_append"},
        {"name": "cmake_list_prepend", "op": "cmake_list_prepend", "value": "cmake_list_prepend"},
    ]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fail_regular_expression(loadtestfile):
    test = loadtestfile["fail_regular_expression"]
    assert find_property(test["properties"], "FAIL_REGULAR_EXPRESSION") == ["This test should fail"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_cleanup(loadtestfile):
    test = loadtestfile["fixtures_cleanup"]
    assert find_property(test["properties"], "FIXTURES_CLEANUP") == ["Foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_required(loadtestfile):
    test = loadtestfile["fixtures_required"]
    assert find_property(test["properties"], "FIXTURES_REQUIRED") == ["Foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_setup(loadtestfile):
    test = loadtestfile["fixtures_setup"]
    assert find_property(test["properties"], "FIXTURES_SETUP") == ["Foo"]


# @pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
# def test_parse_ctesttestfile_generated_resource_spec_file(loadtestfile):
#    test = loadtestfile["generated_resource_spec_file"]
#    assert find_property(test["properties"], "GENERATED_RESOURCE_SPEC_FILE") == "file.txt"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_labels(loadtestfile):
    test = loadtestfile["labels"]
    assert find_property(test["properties"], "LABELS") == ["bar", "foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_measurement_1(loadtestfile):
    test = loadtestfile["measurement_1"]
    assert find_property(test["properties"], "MEASUREMENT") == [
        {"measurement": "foo", "value": "1"}
    ]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_measurement_2(loadtestfile):
    test = loadtestfile["measurement_2"]
    assert find_property(test["properties"], "MEASUREMENT") == [
        {"measurement": "foo", "value": "2"}
    ]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_pass_regular_expression(loadtestfile):
    test = loadtestfile["pass_regular_expression"]
    assert find_property(test["properties"], "PASS_REGULAR_EXPRESSION") == ["passed", "allgood"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_processor_affinity(loadtestfile):
    test = loadtestfile["processor_affinity"]
    assert find_property(test["properties"], "PROCESSOR_AFFINITY") is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_processors(loadtestfile):
    test = loadtestfile["processors"]
    assert find_property(test["properties"], "PROCESSORS") == 5


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_required_files(loadtestfile):
    test = loadtestfile["required_files"]
    assert find_property(test["properties"], "REQUIRED_FILES") == ["foo.txt", "baz.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_resource_groups(loadtestfile):
    test = loadtestfile["resource_groups"]
    resource_groups = find_property(test["properties"], "RESOURCE_GROUPS")
    assert resource_groups == [
        {"requirements": [{".type": "gpus", "slots": 1}]},
        {"requirements": [{".type": "gpus", "slots": 1}]},
        {"requirements": [{".type": "gpus", "slots": 1}]},
        {"requirements": [{".type": "gpus", "slots": 1}]},
        {"requirements": [{".type": "gpus", "slots": 1}]},
    ]
    rg = ctg.parse_resource_groups(resource_groups)
    assert rg == [
        [{"type": "gpus", "slots": 1}],
        [{"type": "gpus", "slots": 1}],
        [{"type": "gpus", "slots": 1}],
        [{"type": "gpus", "slots": 1}],
        [{"type": "gpus", "slots": 1}],
    ]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_resource_lock(loadtestfile):
    test = loadtestfile["resource_lock"]
    assert find_property(test["properties"], "RESOURCE_LOCK") == ["foo.lock"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_run_serial(loadtestfile):
    test = loadtestfile["run_serial"]
    assert find_property(test["properties"], "RUN_SERIAL") is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_skip_regular_expression(loadtestfile):
    test = loadtestfile["skip_regular_expression"]
    assert find_property(test["properties"], "SKIP_REGULAR_EXPRESSION") == ["foo", "bar"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_skip_return_code(loadtestfile):
    test = loadtestfile["skip_return_code"]
    assert find_property(test["properties"], "SKIP_RETURN_CODE") == 3


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout(loadtestfile):
    test = loadtestfile["timeout"]
    assert find_property(test["properties"], "TIMEOUT") == 1


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout_after_match(loadtestfile):
    test = loadtestfile["timeout_after_match"]
    assert find_property(test["properties"], "TIMEOUT_AFTER_MATCH") == {
        "regex": ["foo"],
        "timeout": 1.0,
    }


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout_signal(loadtestfile):
    test = loadtestfile["timeout_signal"]
    assert find_property(test["properties"], "TIMEOUT") == 1
    with pytest.raises(KeyError):
        assert find_property(test["properties"], "TIMEOUT_SIGNAL_NAME") == "SIGINT"
    with pytest.raises(KeyError):
        assert find_property(test["properties"], "TIMEOUT_SIGNAL_GRACE_PERIOD") == "2.0"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_will_fail(loadtestfile):
    test = loadtestfile["will_fail"]
    assert find_property(test["properties"], "WILL_FAIL") is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_working_directory(loadtestfile):
    test = loadtestfile["working_directory"]
    wd = os.getcwd()
    wdt = os.path.abspath(find_property(test["properties"], "WORKING_DIRECTORY"))
    assert wdt == wd


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_cmake_driven_cmd(loadtestfile):
    test = loadtestfile["cmake_driven_cmd"]
    command = test["command"]
    command[0] = os.path.basename(command[0])
    assert command == ["cmake", "-DOPTION=VAL1;VAL2", "-DSPAM=BAZ", "-P", "FILE"]
