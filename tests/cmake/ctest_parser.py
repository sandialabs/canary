import os

import pytest

from _nvtest.plugins.nvtest_ctest.generator import parse
from _nvtest.plugins.nvtest_ctest.generator import parse_np
from _nvtest.util.filesystem import which


@pytest.fixture(scope="module")
def parsetestfile():
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    tests = parse(file)
    return tests


def test_parse_np():
    assert parse_np(["-n", "97"]) == 97
    assert parse_np(["-np", "23"]) == 23
    assert parse_np(["-c", "54"]) == 54
    assert parse_np(["--np", "82"]) == 82
    assert parse_np(["-n765"]) == 765
    assert parse_np(["-np512"]) == 512
    assert parse_np(["-c404"]) == 404
    assert parse_np(["--np=45"]) == 45
    assert parse_np(["--some-arg=4", "--other=foo"]) == 1


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile(parsetestfile):
    assert isinstance(parsetestfile, dict)


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_attached_files(parsetestfile):
    test = parsetestfile["attached_files"]
    assert test["attached_files"] == ["foo.txt", "bar.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_attached_files_on_fail(parsetestfile):
    test = parsetestfile["attached_files_on_fail"]
    assert test["attached_files_on_fail"] == ["foo.txt", "bar.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_cost(parsetestfile):
    test = parsetestfile["cost"]
    assert test["cost"] == 1.0


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_depends(parsetestfile):
    test = parsetestfile["depends"]
    assert test["depends"] == ["attached_files", "cost"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_environment(parsetestfile):
    test = parsetestfile["environment"]
    assert test["environment"] == {"SPAM": "1", "BAZ": "2"}


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_environment_modification(parsetestfile):
    test = parsetestfile["environment_modification"]
    assert test["environment_modification"] == [
        {"op": "set", "name": "set", "value": "set"},
        {"op": "unset", "name": "unset", "value": "unset"},
        {"op": "string_append", "name": "string_append", "value": "string_append"},
        {"op": "string_prepend", "name": "string_prepend", "value": "string_prepend"},
        {"op": "path_list_append", "name": "path_list_append", "value": "path_list_append"},
        {"op": "path_list_prepend", "name": "path_list_prepend", "value": "path_list_prepend"},
        {"op": "cmake_list_append", "name": "cmake_list_append", "value": "cmake_list_append"},
        {"op": "cmake_list_prepend", "name": "cmake_list_prepend", "value": "cmake_list_prepend"},
    ]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fail_regular_expression(parsetestfile):
    test = parsetestfile["fail_regular_expression"]
    assert test["fail_regular_expression"] == ["This test should fail"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_cleanup(parsetestfile):
    test = parsetestfile["fixtures_cleanup"]
    assert test["fixtures_cleanup"] == ["Foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_required(parsetestfile):
    test = parsetestfile["fixtures_required"]
    assert test["fixtures_required"] == ["Foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_fixtures_setup(parsetestfile):
    test = parsetestfile["fixtures_setup"]
    assert test["fixtures_setup"] == ["Foo"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_generated_resource_spec_file(parsetestfile):
    test = parsetestfile["generated_resource_spec_file"]
    assert test["generated_resource_spec_file"] == "file.txt"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_labels(parsetestfile):
    test = parsetestfile["labels"]
    assert test["labels"] == ["foo", "bar"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_measurement_1(parsetestfile):
    test = parsetestfile["measurement_1"]
    assert test["measurement"] == {"foo": 1}


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_measurement_2(parsetestfile):
    test = parsetestfile["measurement_2"]
    assert test["measurement"] == {"foo": 2}


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_pass_regular_expression(parsetestfile):
    test = parsetestfile["pass_regular_expression"]
    assert test["pass_regular_expression"] == ["passed", "allgood"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_processor_affinity(parsetestfile):
    test = parsetestfile["processor_affinity"]
    assert test["processor_affinity"] is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_processors(parsetestfile):
    test = parsetestfile["processors"]
    assert test["processors"] == 5


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_required_files(parsetestfile):
    test = parsetestfile["required_files"]
    assert test["required_files"] == ["foo.txt", "baz.txt"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_resource_groups(parsetestfile):
    test = parsetestfile["resource_groups"]
    assert test["resource_groups"] == ["5,gpus:1"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_resource_lock(parsetestfile):
    test = parsetestfile["resource_lock"]
    assert test["resource_lock"] == ["foo.lock"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_run_serial(parsetestfile):
    test = parsetestfile["run_serial"]
    assert test["run_serial"] is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_skip_regular_expression(parsetestfile):
    test = parsetestfile["skip_regular_expression"]
    assert test["skip_regular_expression"] == ["foo", "bar"]


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_skip_return_code(parsetestfile):
    test = parsetestfile["skip_return_code"]
    assert test["skip_return_code"] == 3


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout(parsetestfile):
    test = parsetestfile["timeout"]
    assert test["timeout"] == 1


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout_after_match(parsetestfile):
    test = parsetestfile["timeout_after_match"]
    assert test["timeout_after_match"] == {"pattern": "foo", "seconds": 1}


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_timeout_signal(parsetestfile):
    test = parsetestfile["timeout_signal"]
    assert test["timeout"] == 1
    assert test["timeout_signal_name"] == "SIGINT"
    assert test["timeout_signal_grace_period"] == 2.0


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_will_fail(parsetestfile):
    test = parsetestfile["will_fail"]
    assert test["will_fail"] is True


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_working_directory(parsetestfile):
    test = parsetestfile["working_directory"]
    assert test["working_directory"] == "."


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_cmake_driven_cmd(parsetestfile):
    test = parsetestfile["cmake_driven_cmd"]
    assert test["args"] == ["cmake", "-DOPTION=VAL1;VAL2", "-DSPAM=BAZ", "-P", "FILE"]
