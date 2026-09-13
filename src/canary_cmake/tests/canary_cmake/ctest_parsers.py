# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_cmake.ctest — pure parser functions (no cmake required)."""

import os

import pytest

from canary_cmake.ctest import apply_env_mods
from canary_cmake.ctest import find_project_binary_dir
from canary_cmake.ctest import infer_project_source_dir
from canary_cmake.ctest import parse_environment
from canary_cmake.ctest import parse_environment_modification
from canary_cmake.ctest import parse_np
from canary_cmake.ctest import parse_resource_groups


# ---------------------------------------------------------------------------
# parse_np
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args, expected",
    [
        # separate flag + value
        (["-n", "4"], 4),
        (["-np", "8"], 8),
        (["-c", "16"], 16),
        (["--np", "2"], 2),
        # combined flag+value
        (["-n4"], 4),
        (["-np8"], 8),
        (["-c16"], 16),
        (["--np=32"], 32),
        # mixed with other args
        (["mpiexec", "-n", "6", "mytest"], 6),
        (["-x", "-n", "3"], 3),
        # no parallelism flag → None
        (["mytest", "--verbose"], None),
        ([], None),
        # zero value → None (safeint(0) is falsy)
        (["-n", "0"], None),
        (["-n0"], None),
    ],
)
def test_parse_np(args, expected):
    assert parse_np(args) == expected


# ---------------------------------------------------------------------------
# apply_env_mods
# ---------------------------------------------------------------------------


def test_apply_env_mods_set():
    mods = [{"op": "set", "name": "MY_VAR", "value": "hello"}]
    result = apply_env_mods(mods)
    assert result["MY_VAR"] == "hello"


def test_apply_env_mods_unset():
    mods = [{"op": "unset", "name": "MY_VAR", "value": ""}]
    result = apply_env_mods(mods)
    assert result["MY_VAR"] is None


def test_apply_env_mods_string_append(monkeypatch):
    monkeypatch.setenv("MY_VAR", "prefix_")
    mods = [{"op": "string_append", "name": "MY_VAR", "value": "suffix"}]
    result = apply_env_mods(mods)
    assert result["MY_VAR"] == "prefix_suffix"


def test_apply_env_mods_string_prepend(monkeypatch):
    monkeypatch.setenv("MY_VAR", "_suffix")
    mods = [{"op": "string_prepend", "name": "MY_VAR", "value": "prefix"}]
    result = apply_env_mods(mods)
    assert result["MY_VAR"] == "prefix_suffix"


def test_apply_env_mods_string_append_unset_var(monkeypatch):
    monkeypatch.delenv("MY_VAR", raising=False)
    mods = [{"op": "string_append", "name": "MY_VAR", "value": "value"}]
    result = apply_env_mods(mods)
    assert result["MY_VAR"] == "value"


def test_apply_env_mods_path_list_append():
    mods = [{"op": "path_list_append", "name": "MY_PATH", "value": "/usr/local"}]
    result = apply_env_mods(mods)
    assert result["MY_PATH"] == "$MY_PATH:/usr/local"


def test_apply_env_mods_path_list_prepend():
    mods = [{"op": "path_list_prepend", "name": "MY_PATH", "value": "/usr/local"}]
    result = apply_env_mods(mods)
    assert result["MY_PATH"] == "/usr/local:$MY_PATH"


def test_apply_env_mods_cmake_list_append():
    mods = [{"op": "cmake_list_append", "name": "MY_LIST", "value": "item"}]
    result = apply_env_mods(mods)
    assert result["MY_LIST"] == "$MY_LIST;item"


def test_apply_env_mods_cmake_list_prepend():
    mods = [{"op": "cmake_list_prepend", "name": "MY_LIST", "value": "item"}]
    result = apply_env_mods(mods)
    assert result["MY_LIST"] == "item;$MY_LIST"


def test_apply_env_mods_multiple_ops():
    mods = [
        {"op": "set", "name": "A", "value": "1"},
        {"op": "set", "name": "B", "value": "2"},
        {"op": "unset", "name": "C", "value": ""},
    ]
    result = apply_env_mods(mods)
    assert result == {"A": "1", "B": "2", "C": None}


def test_apply_env_mods_empty():
    assert apply_env_mods([]) == {}


# ---------------------------------------------------------------------------
# parse_environment
# ---------------------------------------------------------------------------


def test_parse_environment_basic():
    env = parse_environment(["FOO=bar", "BAZ=qux"])
    assert env == {"FOO": "bar", "BAZ": "qux"}


def test_parse_environment_empty():
    assert parse_environment([]) == {}


def test_parse_environment_value_with_equals():
    # split("=", 1) means only first '=' splits
    env = parse_environment(["URL=http://host:8080/path?q=1"])
    assert env["URL"] == "http://host:8080/path?q=1"


def test_parse_environment_preserves_empty_value():
    env = parse_environment(["EMPTY="])
    assert env["EMPTY"] == ""


# ---------------------------------------------------------------------------
# parse_environment_modification
# ---------------------------------------------------------------------------


def test_parse_environment_modification_set():
    items = ["MY_VAR=set:hello"]
    result = parse_environment_modification(items)
    assert len(result) == 1
    assert result[0] == {"name": "MY_VAR", "op": "set", "value": "hello"}


def test_parse_environment_modification_path_append():
    items = ["PATH=path_list_append:/new/dir"]
    result = parse_environment_modification(items)
    assert result[0]["op"] == "path_list_append"
    assert result[0]["value"] == "/new/dir"


def test_parse_environment_modification_multiple():
    items = [
        "VAR_A=set:val_a",
        "VAR_B=string_append:suffix",
    ]
    result = parse_environment_modification(items)
    assert len(result) == 2


def test_parse_environment_modification_empty():
    assert parse_environment_modification([]) == []


def test_parse_environment_modification_skips_non_matching():
    # item without the op:value pattern is silently skipped
    items = ["INVALID_ITEM"]
    result = parse_environment_modification(items)
    assert result == []


# ---------------------------------------------------------------------------
# parse_resource_groups
# ---------------------------------------------------------------------------


def test_parse_resource_groups_basic():
    rg = [
        {"requirements": [{".type": "gpus", "slots": 1}]},
    ]
    result = parse_resource_groups(rg)
    assert len(result) == 1
    assert result[0] == [{"type": "gpus", "slots": 1}]


def test_parse_resource_groups_multiple_requirements():
    rg = [
        {
            "requirements": [
                {".type": "gpus", "slots": 1},
                {".type": "cpus", "slots": 4},
            ]
        }
    ]
    result = parse_resource_groups(rg)
    assert len(result[0]) == 2


def test_parse_resource_groups_empty():
    assert parse_resource_groups([]) == []


# ---------------------------------------------------------------------------
# find_project_binary_dir
# ---------------------------------------------------------------------------


def test_find_project_binary_dir_found(tmp_path):
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "CMakeCache.txt").write_text("# cmake cache\n")
    result = find_project_binary_dir(str(build_dir))
    assert result == str(build_dir)


def test_find_project_binary_dir_nested(tmp_path):
    build_dir = tmp_path / "build"
    nested = build_dir / "sub" / "dir"
    nested.mkdir(parents=True)
    (build_dir / "CMakeCache.txt").write_text("# cmake cache\n")
    result = find_project_binary_dir(str(nested))
    assert result == str(build_dir)


def test_find_project_binary_dir_not_found(tmp_path):
    sub = tmp_path / "noproject" / "sub"
    sub.mkdir(parents=True)
    # No CMakeCache.txt anywhere below tmp_path root
    result = find_project_binary_dir(str(sub))
    assert result is None


# ---------------------------------------------------------------------------
# infer_project_source_dir
# ---------------------------------------------------------------------------


def test_infer_project_source_dir_found(tmp_path):
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    cache = build_dir / "CMakeCache.txt"
    cache.write_text(
        "CMAKE_PROJECT_NAME:STATIC=MyProj\n"
        "MyProj_SOURCE_DIR:STATIC=/path/to/source\n"
    )
    result = infer_project_source_dir(str(build_dir))
    assert result == "/path/to/source"


def test_infer_project_source_dir_not_found(tmp_path):
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "CMakeCache.txt").write_text("# no project name\n")
    result = infer_project_source_dir(str(build_dir))
    assert result is None
