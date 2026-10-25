# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys
from typing import Any

import pytest

import canary_cmake.ctest as ctg
from _canary.util.filesystem import force_remove
from _canary.util.filesystem import which

IS_MACOS = sys.platform == "darwin"


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
    assert ctg.parse_np(["--some-arg=4", "--other=foo"]) is None


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
    if IS_MACOS:
        with pytest.raises(KeyError):
            assert find_property(test["properties"], "TIMEOUT_SIGNAL_NAME") == "SIGINT"
        with pytest.raises(KeyError):
            assert find_property(test["properties"], "TIMEOUT_SIGNAL_GRACE_PERIOD") == 2.0
    else:
        assert find_property(test["properties"], "TIMEOUT_SIGNAL_NAME") == "SIGINT"
        assert find_property(test["properties"], "TIMEOUT_SIGNAL_GRACE_PERIOD") == 2.0


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


def test_parse_np_only_reads_launcher_options():
    # Not an MPI launcher: never read program flags as CPU counts.
    assert ctg.parse_np(["head", "-n", "100", "file"]) is None
    assert ctg.parse_np(["gzip", "-c", "9"]) is None
    assert ctg.parse_np(["sh", "-c", "mpiexec -n 4 exe"]) is None
    assert ctg.parse_np(["echo", "-np", "yaml"]) is None
    # A trailing flag without a value used to raise StopIteration.
    assert ctg.parse_np(["mytool", "-c"]) is None
    assert ctg.parse_np(["mpiexec", "-n"]) is None
    assert ctg.parse_np(["-n"]) is None
    # Launchers
    assert ctg.parse_np(["/usr/bin/mpiexec", "-n", "4", "./a.out", "-n", "99"]) == 4
    assert ctg.parse_np(["mpiexec", "--bind-to", "core", "-n", "8", "exe"]) == 8
    assert ctg.parse_np(["mpirun", "-np", "2", "exe"]) == 2
    assert ctg.parse_np(["srun", "--ntasks=16", "exe"]) == 16
    assert ctg.parse_np(["flux", "run", "-n", "3", "exe"]) == 3
    assert ctg.parse_np(["jsrun", "-n4", "exe"]) == 4


def test_apply_env_mods_operations():
    mods = [
        {"op": "path_list_prepend", "name": "PATH", "value": "/opt/x/bin"},
        {"op": "path_list_append", "name": "LD", "value": "/b"},
        {"op": "set", "name": "A", "value": "1"},
        {"op": "string_append", "name": "A", "value": "2"},
        {"op": "string_prepend", "name": "A", "value": "0"},
        {"op": "cmake_list_append", "name": "L", "value": "z"},
        {"op": "unset", "name": "U", "value": ""},
        {"op": "set", "name": "R", "value": "x"},
        {"op": "reset", "name": "R", "value": ""},
    ]
    out = ctg.apply_env_mods(mods, base={"L": "a;b", "LD": "/a"})
    assert out["PATH"] == "/opt/x/bin:$PATH"
    assert out["LD"] == "/a:/b"
    assert out["A"] == "012"
    assert out["L"] == "a;b;z"
    assert out["U"] is None
    assert "R" not in out


def test_create_ir_with_environment_modification(tmp_path, monkeypatch):
    """ENVIRONMENT_MODIFICATION used to crash generation (unexpected kwarg 'variables')."""
    from pathlib import Path

    from _canary.core.job import Job
    from _canary.execution.testexec import ExecutionSpace

    ctestfile = tmp_path / "CTestTestfile.cmake"
    ctestfile.write_text("")
    monkeypatch.setenv("PATH", "/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin")
    ir = ctg.create_ir(
        file_root=tmp_path,
        file_path="CTestTestfile.cmake",
        family="t",
        ctestfile=str(ctestfile),
        command=["head", "-n", "100", "f"],
        environment={"L": "a;b"},
        environment_modification=[
            {"op": "path_list_prepend", "name": "PATH", "value": "/opt/x/bin"},
            {"op": "cmake_list_append", "name": "L", "value": "z"},
        ],
    )
    # head -n 100 is not a CPU request
    assert "cpus" not in ir.parameters
    spec = ir.finalize({})
    job = Job(spec=spec, workspace=ExecutionSpace(root=tmp_path / "ws", path=Path(spec.exec_path)))
    assert job.variables["L"] == "a;b;z"
    assert (
        job.variables["PATH"]
        == f"{job.workspace.dir}:/opt/x/bin:/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin"
    )


def test_parse_environment_ignores_malformed_entries():
    assert ctg.parse_environment(["A=1", "bad", "B=x=y", "=v"]) == {"A": "1", "B": "x=y"}
