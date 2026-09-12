# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary install`` subcommand.

``canary install`` installs a canary sub-package using the same Python
interpreter that is running canary.

Install target resolution (in priority order):

1. **Editable / local source** — if the canary source tree is present (i.e.
   canary is running from an editable checkout) *and* a ``packages/<name>/``
   subdirectory exists there, install from that directory with ``pip install
   -e``.  This keeps development in sync without any network access.

2. **Git** — ``pip install git+<url>@<commit>#subdirectory=<subdir>`` using
   the coordinates recorded in :data:`CANARY_PACKAGES`.

3. **PyPI** — ``pip install <name>==<version>`` using the coordinates
   recorded in :data:`CANARY_PACKAGES`.  (Future use — not yet published.)

Any arguments after ``--`` on the command line are forwarded verbatim to pip.

Examples::

    canary install canary-distributed-server
    canary install canary-distributed-server -- --index-url http://proxy/simple
    canary install --from source canary-distributed-server
    canary install --from git   canary-distributed-server
    canary install --from pypi  canary-distributed-server
    canary install --list
    canary install              (lists available packages)

Flags must precede the package name; use ``--`` to pass arguments to pip.
"""

import argparse
import importlib.resources as ir
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import TypedDict

from ..hookspec import hookimpl
from ..util import logging
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


logger = logging.get_logger(__name__)


# ---------------------------------------------------------------------------
# Package manifest
# ---------------------------------------------------------------------------


class _PyPIEntry(TypedDict):
    name: str  # PyPI distribution name
    version: str  # known-good version


class _GitEntry(TypedDict):
    url: str  # repository clone URL
    subdirectory: str  # path inside the repo to the package root
    commit: str  # full SHA pinned to a known-good state


class _PackageEntry(TypedDict, total=False):
    pypi: _PyPIEntry
    git: _GitEntry


#: Static manifest of all canary sub-packages.
#:
#: Keys are the logical package names (also the directory names under
#: ``packages/``).  Each entry carries optional ``pypi`` and ``git``
#: coordinates.  At least one of the two must be present for non-source
#: installs to work.
#:
#: Updating this dict is the *only* change needed when a new sub-package is
#: added or a new known-good revision is pinned.
CANARY_PACKAGES: dict[str, _PackageEntry] = {
    "canary-distributed-server": {
        "pypi": {"name": "canary-distributed-server", "version": "0.5"},
        "git": {
            "url": "https://github.com/sandialabs/canary",
            "subdirectory": "packages/canary-distributed-server",
            "commit": "46101e196a46acd71c662a8ba6151cd9acbcd054",
        },
    }
}


# ---------------------------------------------------------------------------
# Subcommand
# ---------------------------------------------------------------------------


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Install())


class Install(CanarySubcommand):
    """Install a canary sub-package using the current Python interpreter.

    The install target is resolved automatically:

    1. Local editable source (``packages/<name>/`` in the canary source tree)
    2. Git (URL + commit from the package manifest)
    3. PyPI (distribution name + version from the package manifest)

    Flags must precede the package name.  Use ``--`` to separate canary flags
    from arguments forwarded to pip::

        canary install canary-distributed-server
        canary install canary-distributed-server -- --index-url http://proxy/simple
        canary install --from git canary-distributed-server
        canary install --list
    """

    name = "install"
    description = "Install a canary sub-package"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_packages",
            help="List available sub-packages and exit.",
        )
        parser.add_argument(
            "--from",
            choices=("auto", "source", "git", "pypi"),
            default="auto",
            dest="install_from",
            metavar="SOURCE",
            help=(
                "Where to install from: "
                "'auto' (default) tries source then git then pypi, "
                "'source' forces local editable install, "
                "'git' forces install from the pinned git commit, "
                "'pypi' forces install from PyPI."
            ),
        )
        parser.add_argument(
            "--editable",
            action="store_true",
            default=True,
            dest="editable",
            help="Install in editable mode when using local source (default: true).",
        )
        parser.add_argument(
            "--no-editable",
            action="store_false",
            dest="editable",
            help="Install as a regular (non-editable) package even from local source.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Print the pip command that would be run without executing it.",
        )
        # Everything after the flags: [PACKAGE] [-- [pip-args...]]
        parser.add_argument(
            "remainder",
            nargs=argparse.REMAINDER,
            metavar="[PACKAGE] [-- [pip-args ...]]",
            help=(
                "Sub-package name, optionally followed by '--' and pip arguments. "
                "Omit to list available packages."
            ),
        )

    def execute(self, args: argparse.Namespace) -> int:
        packages_root = _find_packages_root()

        if args.list_packages:
            return _list_packages(packages_root)

        package, pip_extra = _parse_remainder(args.remainder)

        if package is None:
            return _list_packages(packages_root)

        install_from: str = args.install_from
        editable: bool = args.editable
        dry_run: bool = args.dry_run

        entry = CANARY_PACKAGES.get(package)
        source_dir = _find_source_dir(packages_root, package)

        if install_from == "source":
            if source_dir is None:
                logger.error(
                    f"--from=source requested but packages/{package}/ not found "
                    f"in the canary source tree"
                )
                return 1
            return _install_from_source(
                source_dir, editable=editable, pip_extra=pip_extra, dry_run=dry_run
            )

        if install_from == "git":
            if entry is None or "git" not in entry:
                logger.error(f"No git coordinates in manifest for {package!r}")
                return 1
            return _install_from_git(entry["git"], pip_extra=pip_extra, dry_run=dry_run)

        if install_from == "pypi":
            if entry is None or "pypi" not in entry:
                logger.error(f"No PyPI coordinates in manifest for {package!r}")
                return 1
            return _install_from_pypi(entry["pypi"], pip_extra=pip_extra, dry_run=dry_run)

        # auto: source → git → pypi
        if source_dir is not None:
            logger.info(f"Found local source at {source_dir} — installing from source")
            return _install_from_source(
                source_dir, editable=editable, pip_extra=pip_extra, dry_run=dry_run
            )

        if entry is not None and "git" in entry:
            logger.info(f"No local source for {package!r} — installing from git")
            return _install_from_git(entry["git"], pip_extra=pip_extra, dry_run=dry_run)

        if entry is not None and "pypi" in entry:
            logger.info(f"No git coordinates for {package!r} — installing from PyPI")
            return _install_from_pypi(entry["pypi"], pip_extra=pip_extra, dry_run=dry_run)

        logger.error(
            f"Package {package!r} is not in the manifest and no local source was found.\n"
            f"Run 'canary install --list' to see available packages."
        )
        return 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_remainder(remainder: list[str]) -> tuple[str | None, list[str]]:
    """Split ``[PACKAGE] [-- [pip-args...]]`` from argparse REMAINDER.

    Returns ``(package_name_or_None, pip_extra_args)``.
    """
    if not remainder:
        return None, []

    args = list(remainder)

    # Leading '--': no package name, pip args follow
    if args[0] == "--":
        return None, args[1:]

    package = args[0]
    rest = args[1:]

    # Strip the '--' separator between our args and pip args
    if rest and rest[0] == "--":
        rest = rest[1:]

    return package, rest


def _find_packages_root() -> Path | None:
    """Return the ``packages/`` directory of the canary source tree, or None.

    Uses the same detection strategy as the dev-plugin loader: resolve the
    ``canary`` package location and walk two levels up to the repo root.
    Returns None when canary is not running from an editable checkout.
    """
    try:
        root_traversable = ir.files("canary").joinpath("../..")
        root = Path(os.path.normpath(str(root_traversable)))
    except Exception:
        return None

    packages = root / "packages"
    return packages if packages.is_dir() else None


def _find_source_dir(packages_root: Path | None, package: str) -> Path | None:
    """Return the source directory for *package* if it exists under *packages_root*."""
    if packages_root is None:
        return None
    candidate = packages_root / package
    has_build_file = (candidate / "pyproject.toml").exists() or (candidate / "setup.py").exists()
    return candidate if has_build_file else None


def _list_packages(packages_root: Path | None) -> int:
    """Print known sub-packages and return 0.

    Merges the static manifest with any packages found in the local source
    tree, so the list is correct whether or not a source checkout is present.
    """
    # Start from the manifest; add anything found locally that isn't listed.
    names: set[str] = set(CANARY_PACKAGES)

    if packages_root is not None and packages_root.exists():
        for p in packages_root.iterdir():
            if p.is_dir() and ((p / "pyproject.toml").exists() or (p / "setup.py").exists()):
                names.add(p.name)

    if not names:
        print("No sub-packages available.")
        return 0

    print("Available canary sub-packages:")
    for name in sorted(names):
        entry = CANARY_PACKAGES.get(name, {})
        parts: list[str] = []
        if "pypi" in entry:
            parts.append(f"pypi:{entry['pypi']['version']}")
        if "git" in entry:
            parts.append(f"git:{entry['git']['commit'][:12]}")
        suffix = f"  ({', '.join(parts)})" if parts else ""
        print(f"  {name}{suffix}")
    return 0


def _install_from_source(
    source_dir: Path, *, editable: bool, pip_extra: list[str], dry_run: bool
) -> int:
    """Run ``pip install [-e] <source_dir> [pip_extra]``."""
    cmd = [sys.executable, "-m", "pip", "install"]
    if editable:
        cmd.append("-e")
    cmd.append(str(source_dir))
    cmd.extend(pip_extra)
    return _run_pip(cmd, dry_run=dry_run)


def _install_from_git(entry: "_GitEntry", *, pip_extra: list[str], dry_run: bool) -> int:
    """Run ``pip install git+<url>@<commit>#subdirectory=<subdir> [pip_extra]``."""
    url = entry["url"].rstrip("/")
    commit = entry["commit"]
    subdir = entry["subdirectory"]
    target = f"git+{url}@{commit}#subdirectory={subdir}"
    cmd = [sys.executable, "-m", "pip", "install", target]
    cmd.extend(pip_extra)
    return _run_pip(cmd, dry_run=dry_run)


def _install_from_pypi(entry: "_PyPIEntry", *, pip_extra: list[str], dry_run: bool) -> int:
    """Run ``pip install <name>==<version> [pip_extra]``."""
    target = f"{entry['name']}=={entry['version']}"
    cmd = [sys.executable, "-m", "pip", "install", target]
    cmd.extend(pip_extra)
    return _run_pip(cmd, dry_run=dry_run)


def _run_pip(cmd: list[str], *, dry_run: bool) -> int:
    """Print and optionally execute a pip command."""
    display = " ".join(cmd)
    if dry_run:
        print(f"[dry-run] {display}")
        return 0
    logger.info(f"Running: {display}")
    result = subprocess.run(cmd)
    return result.returncode
