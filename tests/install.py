# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the ``canary install`` subcommand."""

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from _canary.subcommands.install import CANARY_PACKAGES
from _canary.subcommands.install import Install
from _canary.subcommands.install import _find_packages_root
from _canary.subcommands.install import _find_source_dir
from _canary.subcommands.install import _install_from_git
from _canary.subcommands.install import _install_from_pypi
from _canary.subcommands.install import _install_from_source
from _canary.subcommands.install import _list_packages
from _canary.subcommands.install import _parse_remainder

# ---------------------------------------------------------------------------
# _parse_remainder
# ---------------------------------------------------------------------------


class TestParseRemainder:
    def test_empty(self):
        pkg, pip = _parse_remainder([])
        assert pkg is None
        assert pip == []

    def test_package_only(self):
        pkg, pip = _parse_remainder(["canary-distributed-server"])
        assert pkg == "canary-distributed-server"
        assert pip == []

    def test_package_with_pip_args(self):
        pkg, pip = _parse_remainder(
            ["canary-distributed-server", "--", "--index-url", "http://proxy/simple"]
        )
        assert pkg == "canary-distributed-server"
        assert pip == ["--index-url", "http://proxy/simple"]

    def test_separator_only(self):
        """'-- pip-arg' with no package name: package is None, pip args forwarded."""
        pkg, pip = _parse_remainder(["--", "--index-url", "http://proxy/simple"])
        assert pkg is None
        assert pip == ["--index-url", "http://proxy/simple"]

    def test_package_with_no_separator_extra_args(self):
        """No '--' separator: everything after first token is pip extra."""
        pkg, pip = _parse_remainder(["canary-distributed-server", "--no-deps"])
        assert pkg == "canary-distributed-server"
        assert pip == ["--no-deps"]


# ---------------------------------------------------------------------------
# CANARY_PACKAGES manifest
# ---------------------------------------------------------------------------


class TestManifest:
    def test_all_entries_have_at_least_one_source(self):
        for name, entry in CANARY_PACKAGES.items():
            assert "pypi" in entry or "git" in entry, (
                f"{name}: manifest entry must have 'pypi' or 'git' (or both)"
            )

    def test_pypi_entries_have_required_keys(self):
        for name, entry in CANARY_PACKAGES.items():
            if "pypi" in entry:
                assert "name" in entry["pypi"], f"{name}: pypi entry missing 'name'"
                assert "version" in entry["pypi"], f"{name}: pypi entry missing 'version'"

    def test_git_entries_have_required_keys(self):
        for name, entry in CANARY_PACKAGES.items():
            if "git" in entry:
                for key in ("url", "subdirectory", "commit"):
                    assert key in entry["git"], f"{name}: git entry missing {key!r}"

    def test_git_commit_looks_like_full_sha(self):
        for name, entry in CANARY_PACKAGES.items():
            if "git" in entry:
                commit = entry["git"]["commit"]
                assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), (
                    f"{name}: git.commit should be a full 40-char hex SHA, got {commit!r}"
                )

    def test_distributed_server_present(self):
        assert "canary-distributed-server" in CANARY_PACKAGES

    def test_distributed_server_git_url(self):
        entry = CANARY_PACKAGES["canary-distributed-server"]
        assert "git" in entry
        assert "github.com/sandialabs/canary" in entry["git"]["url"]
        assert entry["git"]["subdirectory"] == "packages/canary-distributed-server"


# ---------------------------------------------------------------------------
# _find_packages_root
# ---------------------------------------------------------------------------


class TestFindPackagesRoot:
    def test_returns_none_when_no_packages_dir(self, tmp_path):
        fake_root = str(tmp_path)
        mock_traversable = MagicMock()
        mock_traversable.__str__ = lambda s: fake_root
        with patch("_canary.subcommands.install.ir.files") as mock_files:
            mock_files.return_value.joinpath.return_value = mock_traversable
            result = _find_packages_root()
        assert result is None

    def test_returns_path_when_packages_dir_exists(self, tmp_path):
        (tmp_path / "packages").mkdir()
        # Patch _find_packages_root's internal Path resolution directly
        with patch("_canary.subcommands.install.ir.files") as mock_files:
            # joinpath("../..") on a fake traversable should stringify to tmp_path
            mock_traversable = MagicMock()
            mock_traversable.__str__ = MagicMock(return_value=str(tmp_path))
            mock_files.return_value.joinpath.return_value = mock_traversable
            result = _find_packages_root()
        assert result == tmp_path / "packages"


# ---------------------------------------------------------------------------
# _find_source_dir
# ---------------------------------------------------------------------------


class TestFindSourceDir:
    def test_returns_none_when_root_is_none(self):
        assert _find_source_dir(None, "any-pkg") is None

    def test_returns_none_when_package_missing(self, tmp_path):
        packages = tmp_path / "packages"
        packages.mkdir()
        assert _find_source_dir(packages, "canary-missing") is None

    def test_finds_package_with_pyproject(self, tmp_path):
        packages = tmp_path / "packages"
        pkg_dir = packages / "canary-distributed-server"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        assert _find_source_dir(packages, "canary-distributed-server") == pkg_dir

    def test_finds_package_with_setup_py(self, tmp_path):
        packages = tmp_path / "packages"
        pkg_dir = packages / "canary-other"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "setup.py").write_text("from setuptools import setup; setup()\n")
        assert _find_source_dir(packages, "canary-other") == pkg_dir

    def test_returns_none_when_dir_has_no_build_file(self, tmp_path):
        packages = tmp_path / "packages"
        (packages / "canary-empty").mkdir(parents=True)
        assert _find_source_dir(packages, "canary-empty") is None


# ---------------------------------------------------------------------------
# _list_packages
# ---------------------------------------------------------------------------


class TestListPackages:
    def test_none_root_still_shows_manifest(self, capsys):
        rc = _list_packages(None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "canary-distributed-server" in out

    def test_shows_version_and_sha_prefix(self, capsys):
        _list_packages(None)
        out = capsys.readouterr().out
        # pypi version should appear
        assert "0.5" in out
        # git SHA prefix (12 chars) should appear
        sha12 = CANARY_PACKAGES["canary-distributed-server"]["git"]["commit"][:12]
        assert sha12 in out

    def test_merges_local_packages_not_in_manifest(self, tmp_path, capsys):
        packages = tmp_path / "packages"
        pkg_dir = packages / "canary-custom"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text("[project]\n")
        _list_packages(packages)
        out = capsys.readouterr().out
        assert "canary-custom" in out
        assert "canary-distributed-server" in out

    def test_ignores_dirs_without_build_file(self, tmp_path, capsys):
        packages = tmp_path / "packages"
        (packages / "canary-junk").mkdir(parents=True)
        _list_packages(packages)
        out = capsys.readouterr().out
        assert "canary-junk" not in out


# ---------------------------------------------------------------------------
# _install_from_source
# ---------------------------------------------------------------------------


class TestInstallFromSource:
    def test_dry_run_editable(self, tmp_path, capsys):
        src = tmp_path / "canary-distributed-server"
        src.mkdir()
        rc = _install_from_source(src, editable=True, pip_extra=[], dry_run=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[dry-run]" in out
        assert "-e" in out
        assert str(src) in out

    def test_dry_run_no_editable(self, tmp_path, capsys):
        src = tmp_path / "canary-distributed-server"
        src.mkdir()
        rc = _install_from_source(src, editable=False, pip_extra=[], dry_run=True)
        assert rc == 0
        assert "-e" not in capsys.readouterr().out

    def test_dry_run_pip_extra_forwarded(self, tmp_path, capsys):
        src = tmp_path / "canary-distributed-server"
        src.mkdir()
        _install_from_source(
            src, editable=True, pip_extra=["--index-url", "http://proxy/simple"], dry_run=True
        )
        out = capsys.readouterr().out
        assert "--index-url" in out and "http://proxy/simple" in out

    def test_runs_correct_pip_command(self, tmp_path):
        src = tmp_path / "canary-distributed-server"
        src.mkdir()
        captured: list[list[str]] = []
        with patch(
            "_canary.subcommands.install.subprocess.run",
            side_effect=lambda cmd, **_: captured.append(cmd) or MagicMock(returncode=0),
        ):
            rc = _install_from_source(src, editable=True, pip_extra=[], dry_run=False)
        assert rc == 0
        assert captured[0] == [sys.executable, "-m", "pip", "install", "-e", str(src)]

    def test_returns_pip_returncode(self, tmp_path):
        src = tmp_path / "canary-distributed-server"
        src.mkdir()
        with patch(
            "_canary.subcommands.install.subprocess.run", return_value=MagicMock(returncode=2)
        ):
            assert _install_from_source(src, editable=True, pip_extra=[], dry_run=False) == 2


# ---------------------------------------------------------------------------
# _install_from_git
# ---------------------------------------------------------------------------


class TestInstallFromGit:
    _entry = {
        "url": "https://github.com/sandialabs/canary",
        "subdirectory": "packages/canary-distributed-server",
        "commit": "46101e196a46acd71c662a8ba6151cd9acbcd054",
    }

    def test_dry_run_url_contains_commit_and_subdir(self, capsys):
        rc = _install_from_git(self._entry, pip_extra=[], dry_run=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[dry-run]" in out
        assert "46101e196a46acd71c662a8ba6151cd9acbcd054" in out
        assert "subdirectory=packages/canary-distributed-server" in out
        assert "github.com/sandialabs/canary" in out

    def test_dry_run_pip_extra_forwarded(self, capsys):
        _install_from_git(
            self._entry, pip_extra=["--index-url", "http://proxy/simple"], dry_run=True
        )
        assert "--index-url" in capsys.readouterr().out

    def test_runs_correct_pip_command(self):
        captured: list[list[str]] = []
        with patch(
            "_canary.subcommands.install.subprocess.run",
            side_effect=lambda cmd, **_: captured.append(cmd) or MagicMock(returncode=0),
        ):
            _install_from_git(self._entry, pip_extra=[], dry_run=False)
        cmd = captured[0]
        assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
        target = cmd[4]
        assert "46101e196a46acd71c662a8ba6151cd9acbcd054" in target
        assert "subdirectory=packages/canary-distributed-server" in target


# ---------------------------------------------------------------------------
# _install_from_pypi
# ---------------------------------------------------------------------------


class TestInstallFromPyPI:
    _entry = {"name": "canary-distributed-server", "version": "0.5"}

    def test_dry_run_uses_pinned_version(self, capsys):
        rc = _install_from_pypi(self._entry, pip_extra=[], dry_run=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "canary-distributed-server==0.5" in out

    def test_dry_run_pip_extra_forwarded(self, capsys):
        _install_from_pypi(
            self._entry, pip_extra=["--index-url", "http://proxy/simple"], dry_run=True
        )
        assert "--index-url" in capsys.readouterr().out

    def test_runs_correct_pip_command(self):
        captured: list[list[str]] = []
        with patch(
            "_canary.subcommands.install.subprocess.run",
            side_effect=lambda cmd, **_: captured.append(cmd) or MagicMock(returncode=0),
        ):
            _install_from_pypi(self._entry, pip_extra=[], dry_run=False)
        assert captured[0] == [
            sys.executable,
            "-m",
            "pip",
            "install",
            "canary-distributed-server==0.5",
        ]


# ---------------------------------------------------------------------------
# Install.execute — integration through the subcommand object
# ---------------------------------------------------------------------------


def _args(**kwargs) -> argparse.Namespace:
    defaults = {
        "list_packages": False,
        "install_from": "auto",
        "editable": True,
        "dry_run": True,
        "remainder": [],
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _pkg_dir(tmp_path: Path) -> Path:
    """Create a minimal local package directory and return it."""
    d = tmp_path / "packages" / "canary-distributed-server"
    d.mkdir(parents=True)
    (d / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    return d


class TestInstallExecute:
    def test_no_args_lists_packages(self, capsys):
        rc = Install().execute(_args())
        assert rc == 0
        assert "canary-distributed-server" in capsys.readouterr().out

    def test_list_flag_lists_packages(self, capsys):
        rc = Install().execute(_args(list_packages=True))
        assert rc == 0
        assert "canary-distributed-server" in capsys.readouterr().out

    def test_auto_picks_source_when_available(self, tmp_path, capsys):
        pkg = _pkg_dir(tmp_path)
        with patch(
            "_canary.subcommands.install._find_packages_root",
            return_value=pkg.parent.parent / "packages",
        ):
            rc = Install().execute(_args(remainder=["canary-distributed-server"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[dry-run]" in out and "-e" in out and str(pkg) in out

    def test_auto_falls_back_to_git_when_no_source(self, tmp_path, capsys):
        empty = tmp_path / "packages"
        empty.mkdir()
        with patch("_canary.subcommands.install._find_packages_root", return_value=empty):
            rc = Install().execute(_args(remainder=["canary-distributed-server"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "github.com/sandialabs/canary" in out

    def test_force_git(self, tmp_path, capsys):
        pkg = _pkg_dir(tmp_path)
        with patch(
            "_canary.subcommands.install._find_packages_root",
            return_value=pkg.parent.parent / "packages",
        ):
            rc = Install().execute(
                _args(remainder=["canary-distributed-server"], install_from="git")
            )
        assert rc == 0
        out = capsys.readouterr().out
        assert "github.com/sandialabs/canary" in out

    def test_force_pypi(self, tmp_path, capsys):
        pkg = _pkg_dir(tmp_path)
        with patch(
            "_canary.subcommands.install._find_packages_root",
            return_value=pkg.parent.parent / "packages",
        ):
            rc = Install().execute(
                _args(remainder=["canary-distributed-server"], install_from="pypi")
            )
        assert rc == 0
        assert "canary-distributed-server==0.5" in capsys.readouterr().out

    def test_force_source_missing_returns_error(self, tmp_path):
        empty = tmp_path / "packages"
        empty.mkdir()
        with patch("_canary.subcommands.install._find_packages_root", return_value=empty):
            rc = Install().execute(
                _args(remainder=["canary-distributed-server"], install_from="source")
            )
        assert rc == 1

    def test_unknown_package_no_manifest_no_source_returns_error(self, tmp_path):
        empty = tmp_path / "packages"
        empty.mkdir()
        with patch("_canary.subcommands.install._find_packages_root", return_value=empty):
            rc = Install().execute(_args(remainder=["canary-nonexistent"]))
        assert rc == 1

    def test_pip_extra_forwarded_via_separator(self, tmp_path, capsys):
        pkg = _pkg_dir(tmp_path)
        with patch(
            "_canary.subcommands.install._find_packages_root",
            return_value=pkg.parent.parent / "packages",
        ):
            rc = Install().execute(
                _args(
                    remainder=[
                        "canary-distributed-server",
                        "--",
                        "--index-url",
                        "http://proxy/simple",
                    ],
                    install_from="source",
                )
            )
        assert rc == 0
        out = capsys.readouterr().out
        assert "--index-url" in out and "http://proxy/simple" in out

    def test_git_missing_from_manifest_returns_error(self, tmp_path):
        empty = tmp_path / "packages"
        empty.mkdir()
        # Patch manifest to have an entry with no git key
        manifest_patch = {"canary-no-git": {"pypi": {"name": "canary-no-git", "version": "1.0"}}}
        with patch("_canary.subcommands.install._find_packages_root", return_value=empty):
            with patch("_canary.subcommands.install.CANARY_PACKAGES", manifest_patch):
                rc = Install().execute(_args(remainder=["canary-no-git"], install_from="git"))
        assert rc == 1

    def test_pypi_missing_from_manifest_returns_error(self, tmp_path):
        empty = tmp_path / "packages"
        empty.mkdir()
        manifest_patch = {
            "canary-git-only": {
                "git": {
                    "url": "https://github.com/example/repo",
                    "subdirectory": "packages/canary-git-only",
                    "commit": "a" * 40,
                }
            }
        }
        with patch("_canary.subcommands.install._find_packages_root", return_value=empty):
            with patch("_canary.subcommands.install.CANARY_PACKAGES", manifest_patch):
                rc = Install().execute(_args(remainder=["canary-git-only"], install_from="pypi"))
        assert rc == 1
