# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Parameters and job paths must never let a job escape the session directory."""

from pathlib import Path

import pytest

from _canary.core.jobspec import UnsafeParameterError
from _canary.core.jobspec_ir import JobSpecIR
from _canary.execution.testexec import ExecutionSpace


@pytest.fixture
def testfile(tmp_path: Path) -> Path:
    f = tmp_path / "t.pyt"
    f.write_text("")
    return f


def _ir(testfile: Path, **kwargs) -> JobSpecIR:
    return JobSpecIR(file_root=testfile.parent, file_path=Path(testfile.name), **kwargs)


@pytest.mark.parametrize(
    "value", ["x/../../../../victim", "a/b", "/abs", "a\\b", "\x00", "line\nbreak", "tab\there"]
)
def test_unsafe_parameter_values_rejected(testfile, value):
    with pytest.raises(UnsafeParameterError):
        _ir(testfile, parameters={"p": value})


@pytest.mark.parametrize("name", ["a/b", "..", "", "x\x00"])
def test_unsafe_parameter_names_rejected(testfile, name):
    with pytest.raises(UnsafeParameterError):
        _ir(testfile, parameters={name: 1})


@pytest.mark.parametrize("value", [1, 2.5, "gcc-12", "a b", "x=y", "..", "", "ünïcode", True])
def test_safe_parameter_values_accepted(testfile, value):
    ir = _ir(testfile, parameters={"p": value})
    spec = ir.finalize({})
    assert spec.exec_path.parent == Path(".")
    assert "/" not in spec.exec_path.name


@pytest.mark.parametrize("path", ["../x", "/abs/path", "a/../../b"])
def test_unsafe_exec_and_view_paths_rejected(testfile, path):
    with pytest.raises(UnsafeParameterError):
        _ir(testfile, exec_path=path)
    with pytest.raises(UnsafeParameterError):
        _ir(testfile, view_path=path)


def test_nested_relative_exec_path_allowed(testfile):
    spec = _ir(testfile, exec_path="custom/exec/dir").finalize({})
    assert spec.exec_path == Path("custom/exec/dir")


def test_unsafe_family_rejected(testfile):
    with pytest.raises(UnsafeParameterError):
        _ir(testfile, family="..")


def test_execution_space_refuses_to_escape_root(tmp_path: Path):
    root = tmp_path / "session"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep")

    space = ExecutionSpace(root=root, path=Path("../victim"))
    with pytest.raises(ValueError):
        space.remove()
    with pytest.raises(ValueError):
        space.create(exist_ok=True)
    assert (victim / "precious.txt").exists()


def test_execution_space_refuses_symlink_escape(tmp_path: Path):
    root = tmp_path / "session"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep")
    (root / "link").symlink_to(victim, target_is_directory=True)

    space = ExecutionSpace(root=root, path=Path("link/sub"))
    with pytest.raises(ValueError):
        space.create(exist_ok=True)
    assert not (victim / "sub").exists()


def test_execution_space_normal_paths(tmp_path: Path):
    root = tmp_path / "session"
    root.mkdir()
    space = ExecutionSpace(root=root, path=Path("a/b/t.p=1"))
    space.create()
    assert space.exists()
    space.remove()
    assert not space.exists()
