# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.editor — text editor finder/invoker."""

import os

import pytest

from _canary.util.editor import _find_exe_from_env_var
from _canary.util.editor import editor
from _canary.util.filesystem import which


# ---------------------------------------------------------------------------
# _find_exe_from_env_var
# ---------------------------------------------------------------------------


def test_find_exe_returns_none_when_var_unset(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    result = _find_exe_from_env_var("VISUAL")
    assert result is None


def test_find_exe_returns_none_when_var_empty(monkeypatch):
    monkeypatch.setenv("VISUAL", "")
    result = _find_exe_from_env_var("VISUAL")
    assert result is None


def test_find_exe_returns_none_when_not_executable(monkeypatch, tmp_path):
    monkeypatch.setenv("VISUAL", "/nonexistent/editor_xyz")
    result = _find_exe_from_env_var("VISUAL")
    assert result is None


def test_find_exe_returns_namespace_for_valid_exe(monkeypatch, tmp_path):
    # Create a fake executable
    fake_exe = tmp_path / "myeditor"
    fake_exe.write_text("#!/bin/sh\n")
    fake_exe.chmod(0o755)

    monkeypatch.setenv("VISUAL", str(fake_exe))
    result = _find_exe_from_env_var("VISUAL")
    assert result is not None
    assert result.path == str(fake_exe)
    assert result.default_args == [str(fake_exe)]


def test_find_exe_with_extra_args(monkeypatch, tmp_path):
    fake_exe = tmp_path / "myeditor"
    fake_exe.write_text("#!/bin/sh\n")
    fake_exe.chmod(0o755)

    monkeypatch.setenv("VISUAL", f"{fake_exe} --wait --nofork")
    result = _find_exe_from_env_var("VISUAL")
    assert result is not None
    assert result.path == str(fake_exe)
    assert result.default_args == [str(fake_exe), "--wait", "--nofork"]


# ---------------------------------------------------------------------------
# editor() — with injectable exec_fn
# ---------------------------------------------------------------------------


def _noop_exec(path, args):
    """exec_fn that succeeds immediately without really exec-ing."""
    return 0


def _fail_exec(path, args):
    """exec_fn that always fails."""
    return 1


def test_editor_uses_visual_first(monkeypatch, tmp_path):
    fake_exe = tmp_path / "visual_editor"
    fake_exe.write_text("#!/bin/sh\n")
    fake_exe.chmod(0o755)
    monkeypatch.setenv("VISUAL", str(fake_exe))
    monkeypatch.delenv("EDITOR", raising=False)

    invoked = []

    def tracking_exec(path, args):
        invoked.append(path)
        return 0

    result = editor("file.txt", exec_fn=tracking_exec)
    assert result is True
    assert str(fake_exe) in invoked[0]


def test_editor_falls_back_to_editor_var(monkeypatch, tmp_path):
    fake_exe = tmp_path / "my_editor"
    fake_exe.write_text("#!/bin/sh\n")
    fake_exe.chmod(0o755)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", str(fake_exe))

    invoked = []

    def tracking_exec(path, args):
        invoked.append(path)
        return 0

    result = editor("file.txt", exec_fn=tracking_exec)
    assert result is True
    assert str(fake_exe) in invoked[0]


def test_editor_falls_back_to_default_editors(monkeypatch, tmp_path):
    fake_vi = tmp_path / "vi"
    fake_vi.write_text("#!/bin/sh\n")
    fake_vi.chmod(0o755)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    import _canary.util.editor as editor_mod

    monkeypatch.setattr(editor_mod, "_default_editors", [str(fake_vi)])

    result = editor("file.txt", exec_fn=_noop_exec)
    assert result is True


def test_editor_raises_when_nothing_found(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    import _canary.util.editor as editor_mod

    monkeypatch.setattr(editor_mod, "_default_editors", [])

    with pytest.raises(ValueError, match="No text editor found"):
        editor("file.txt", exec_fn=_noop_exec)


def test_editor_visual_not_executable_falls_back(monkeypatch, tmp_path):
    """If VISUAL points to something that can't be exec'd, fall back to EDITOR."""
    fake_editor = tmp_path / "fallback_editor"
    fake_editor.write_text("#!/bin/sh\n")
    fake_editor.chmod(0o755)
    # VISUAL points to a non-existent path
    monkeypatch.setenv("VISUAL", "/nonexistent/editor_xyz")
    monkeypatch.setenv("EDITOR", str(fake_editor))

    invoked = []

    def tracking_exec(path, args):
        invoked.append(path)
        return 0

    result = editor("file.txt", exec_fn=tracking_exec)
    assert result is True
    assert str(fake_editor) in invoked[0]
