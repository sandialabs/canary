# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

import canary
from _canary.util.filesystem import working_dir
from _canary.view import ViewSettings
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_workspace_run_creates_owned_view(tmp_path):
    root = tmp_path / "view-owned"
    root.mkdir()

    write(
        root / "a.pyt",
        """\
import sys

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        session = workspace.run(specs, only="all")

        assert session.returncode == 0

        view = root / "TestResults"
        assert view.exists()
        assert (view / ".canary-view.json").exists()
        assert (view / "a").exists()


def test_rebuild_owned_view_smoke(tmp_path):
    root = tmp_path / "view-rebuild"
    root.mkdir()

    write(
        root / "a.pyt",
        """\
import sys

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        session = workspace.run(specs, only="all")

        assert session.returncode == 0

        view = root / "TestResults"
        assert view.exists()
        assert (view / ".canary-view.json").exists()
        assert (view / "a").exists()

        workspace.rebuild_view(
            view_t=ViewSettings(when="always", only="all", mode="symlink", name="TestResults")
        )

        assert view.exists()
        assert (view / ".canary-view.json").exists()
        assert (view / "a").exists()


def test_rebuild_view_refuses_non_owning_directory(tmp_path):
    root = tmp_path / "view-non-owned"
    root.mkdir()

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)

        view = root / "TestResults"
        view.mkdir()
        (view / "user-file.txt").write_text("do not delete")

        with pytest.raises(ValueError, match="non-owning directory"):
            workspace.rebuild_view(
                view_t=ViewSettings(when="always", only="all", mode="symlink", name="TestResults")
            )

        assert (view / "user-file.txt").exists()
