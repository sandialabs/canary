# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from _canary.core.execspace import ExecutionSpace
from _canary.util import json_helper as json


def test_joinpath_rejects_absolute_path(tmp_path):
    space = ExecutionSpace(root=tmp_path, path=Path("work"))

    with pytest.raises(ValueError, match="absolute paths not allowed"):
        space.joinpath("/etc/passwd")


def test_joinpath_rejects_parent_escape(tmp_path):
    space = ExecutionSpace(root=tmp_path, path=Path("work"))
    space.create(exist_ok=True)

    with pytest.raises(ValueError, match="path escapes base directory"):
        space.joinpath("..", "outside.txt")


def test_openfile_creates_parent_dirs_inside_workspace(tmp_path):
    space = ExecutionSpace(root=tmp_path, path=Path("work"))
    space.create(exist_ok=True)

    with space.openfile("a/b/c.txt", "w") as fh:
        fh.write("hello")

    assert (space.dir / "a" / "b" / "c.txt").read_text() == "hello"


def test_openfile_rejects_escape(tmp_path):
    space = ExecutionSpace(root=tmp_path, path=Path("work"))
    space.create(exist_ok=True)

    with pytest.raises(ValueError):
        with space.openfile("../bad.txt", "w"):
            pass


def test_round_trip_and_legacy_type_tag(tmp_path):
    """Lock files written before ExecutionSpace moved to core still load."""
    space = ExecutionSpace(root=tmp_path, path=Path("work"))
    text = json.dumps(space)
    assert '"_canary.core.execspace::ExecutionSpace"' in text
    legacy = text.replace("_canary.core.execspace::", "_canary.execution.testexec::")

    for blob in (text, legacy):
        loaded = json.loads(blob)
        assert isinstance(loaded, ExecutionSpace)
        assert (loaded.root, loaded.path) == (space.root, space.path)
