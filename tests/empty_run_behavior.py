# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

import canary
from _canary.error import StopExecution
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_workspace_run_empty_specs_raises_notests(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)

        with pytest.raises(StopExecution) as exc:
            workspace.run([], only="all")

        assert exc.value.exit_code == 7


def test_workspace_run_all_masked_specs_raises_notests(tmp_path):
    root = tmp_path / "all-masked"
    root.mkdir()

    write(
        root / "disabled.pyt",
        """\
import canary_pyt
canary_pyt.directives.enable(False)
def test():
    raise AssertionError("should not run")
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="all")

        assert exc.value.exit_code == 7


def test_only_changed_with_no_changes_raises_notests(tmp_path):
    root = tmp_path / "no-changes"
    root.mkdir()

    write(
        root / "case.pyt",
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

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="changed")

        assert exc.value.exit_code == 7


def test_only_not_pass_after_all_pass_raises_notests(tmp_path):
    root = tmp_path / "all-pass"
    root.mkdir()

    write(
        root / "case.pyt",
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

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="not_pass")

        assert exc.value.exit_code == 7
