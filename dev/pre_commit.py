# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Developer-only ``canary pre-commit`` / ``canary check`` subcommand.

This module is **not** part of the installed canary package.  It lives in the
``dev/`` directory at the repository root and is only loaded by
:class:`_canary.pluginmanager.CanaryPluginManager` when canary is running from
an editable checkout that has the ``dev/`` directory present next to ``.git/``.

The public surface exposed to canary's plugin system is the
:func:`canary_addcommand` hook implementation in :mod:`dev.__init__`.  This
module contains the full implementation.
"""

import argparse
import datetime
import importlib.resources as ir
import os
import re
import shutil
import site
import subprocess
import sys
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path
from typing import Any
from typing import Sequence

from _canary.subcommands.base import CanarySubcommand
from _canary.util import logging
from _canary.util.filesystem import working_dir
from _canary.util.pytest_runner import PytestResult
from _canary.util.pytest_runner import run_pytest_one

stdout: Any = subprocess.PIPE
stderr: Any = subprocess.PIPE

logger = logging.get_logger(__name__)


class Action(argparse.Action):
    """Accumulate single-character flag letters into ``namespace.action``."""

    def __call__(self, parser, namespace, values, option_string=None):
        action = getattr(namespace, "action", set())
        assert option_string is not None
        value = option_string[1:]
        action.add(value)
        namespace.action = action


class Check(CanarySubcommand):
    """Run canary's internal code-quality and pre-commit checks.

    Orchestrates formatting (ruff), lint checking (ruff), type checking (ty or
    mypy), security scanning (bandit), pytest test runs (optionally with
    coverage), Sphinx documentation builds, and version stamping.
    Checks run only from an editable install of the Canary repository.
    """

    name = "pre-commit"
    description = "Run canary's internal checks"
    add_help = False
    aliases = ["check"]

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        """Register check flags (-f format, -c lint, -m type, -b bandit, -t test, etc.)."""
        parser.add_argument(
            "-l", nargs=0, action=Action, help="add missing license headers (default)"
        )
        parser.add_argument("-f", nargs=0, action=Action, help="run ruff format (default)")
        parser.add_argument("-c", nargs=0, action=Action, help="run ruff check (default)")
        parser.add_argument("-m", nargs=0, action=Action, help="run mypy (default)")
        parser.add_argument(
            "-b", nargs=0, action=Action, help="run bandit security checks (default)"
        )
        parser.add_argument("-t", nargs=0, action=Action, help="run pytest (default)")
        parser.add_argument("-C", nargs=0, action=Action, help="run coverage")
        parser.add_argument("-e", nargs=0, action=Action, help="run examples test")
        parser.add_argument("-d", nargs=0, action=Action, help="make docs")
        parser.add_argument("--verbose", action="store_true", help="verbose")
        parser.add_argument(
            "--local-packages",
            choices=("yes", "no"),
            default="no" if "VIRTUAL_ENV" in os.environ else "yes",
            dest="use_local_packages",
            help="Add local site-packages to search path when running type checker",
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Run the selected checks and return 0 on success, raising on any failure."""
        global stdout
        global stderr

        if args.verbose:
            stdout = sys.stdout
            stderr = sys.stderr

        root = ir.files("canary").joinpath("../..")
        if not root.joinpath(".git").is_dir():
            raise ValueError("canary pre-commit must be run from an editable install of canary")

        self.root = os.path.normpath(str(root))

        if not hasattr(args, "action"):
            args.action = set("lfcmbt")

        if shutil.which("ruff") is None and "f" in args.action:
            raise ValueError("ruff must be on PATH to format and check code")
        if shutil.which("ruff") is None and "c" in args.action:
            raise ValueError("ruff must be on PATH to lint check code")
        if shutil.which("bandit") is None and "b" in args.action:
            raise ValueError("bandit must be on PATH to format and check code")
        if "m" in args.action:
            if shutil.which("ty") is None and shutil.which("mypy") is None:
                raise ValueError("type checking requires ty or mypy be on PATH")
        if "t" in args.action or "C" in args.action:
            if shutil.which("pytest") is None:
                raise ValueError("pytest must be on PATH to test code")
            if shutil.which("coverage") is None and "C" in args.action:
                raise ValueError("coverage must be on PATH to run coverage")

        if "l" in args.action:
            self.add_licenses(args)

        if "f" in args.action:
            self.format_code(args)

        if "c" in args.action:
            self.lint_check_code(args)

        if "b" in args.action and shutil.which("bandit"):
            self.security_check(args)

        if "m" in args.action:
            self.type_check_code(args)

        if "t" in args.action or "C" in args.action:
            self.run_tests(args)

        if "d" in args.action:
            self.make_docs(args)

        # All selected checks passed: stamp the date-based version
        # unconditionally.
        self.stamp_version(args)

        logger.info("All checks complete!")

        return 0

    def stamp_version(self, args: argparse.Namespace) -> None:
        """Update ``pyproject.toml`` project.version to today's YY.M.D value."""
        today = datetime.date.today()
        version = f"{today.year % 100}.{today.month}.{today.day}"
        update_pyproject_version(Path(self.root), version)

    @staticmethod
    def find_pyt_files(top: str) -> list[str]:
        """Recursively collect ``.pyt`` file paths under *top*."""
        pyt_files: list[str] = []

        for dirname, _, files in os.walk(top):
            pyt_files.extend([os.path.join(dirname, f) for f in files if f.endswith(".pyt")])

        return pyt_files

    def add_licenses(self, args: argparse.Namespace):
        """Add missing SPDX license headers to source, docs, and test trees."""
        with working_dir(self.root):
            pm = logger.progress_monitor(f"Adding missing license headers in {self.root}")
            for top in ("./src", "./docs", "./tests", "./bin", "./dev"):
                if os.path.isdir(top):
                    add_licenses(top)
            pm.done()

    def format_code(self, args: argparse.Namespace):
        """Run ``ruff format`` over all source, docs, and test trees."""
        with working_dir(self.root):
            pm = logger.progress_monitor(
                f"Formatting examples in {self.root}/src/canary/docs/examples"
            )
            paths = Check.find_pyt_files("./src/canary/docs/examples")
            ruff("format", *paths)
            ruff("format", "./src/canary")
            pm.done()

            pm = logger.progress_monitor(f"Formatting examples in {self.root}/docs")
            ruff("format", "./docs")
            pm.done()

            pm = logger.progress_monitor(f"Formatting tests in {self.root}/tests")
            ruff("format", "./tests")
            pm.done()

            pm = logger.progress_monitor(f"Formatting source in {self.root}/src")
            ruff("format", "./src")
            pm.done()

            pm = logger.progress_monitor(f"Formatting dev in {self.root}/dev")
            ruff("format", "./dev")
            pm.done()

            if os.path.isdir("./packages"):
                pm = logger.progress_monitor(f"Formatting packages in {self.root}/packages")
                ruff("format", "./packages")
                pm.done()

    def lint_check_code(self, args: argparse.Namespace):
        """Run ``ruff check --fix`` over all source, docs, and test trees."""
        with working_dir(self.root):
            pm = logger.progress_monitor(
                f"Lint checking examples in {self.root}/src/canary/docs/examples"
            )
            paths = Check.find_pyt_files("./src/canary/docs/examples")
            ruff_check(*paths)
            ruff_check("./src/canary/docs")
            ruff_check("./docs")
            ruff_check("./bin")
            paths = Check.find_pyt_files("./docs")
            ruff_check(*paths)
            pm.done()

            pm = logger.progress_monitor(
                f"Lint checking examples in {self.root}/docs/source/static"
            )
            ruff_check("./docs/source/static")
            pm.done()

            pm = logger.progress_monitor(f"Lint checking tests in {self.root}/tests")
            ruff_check("./tests")
            pm.done()

            pm = logger.progress_monitor(f"Lint checking source in {self.root}/src")
            ruff_check("./src")
            pm.done()

            pm = logger.progress_monitor(f"Lint checking dev in {self.root}/dev")
            ruff_check("./dev")
            pm.done()

            if os.path.isdir("./packages"):
                pm = logger.progress_monitor(f"Lint checking packages in {self.root}/packages")
                ruff_check("./packages")
                pm.done()

    def security_check(self, args: argparse.Namespace):
        """Run bandit security scan over ``src/``."""
        with working_dir(self.root):
            pm = logger.progress_monitor("Checking source for security violations")
            bandit("-c", "./pyproject.toml", "-r", "src/")
            pm.done()

    def type_check_code(self, args: argparse.Namespace):
        """Run ty or mypy type checking over ``src/``."""
        with working_dir(self.root):
            pm = logger.progress_monitor(f"Type checking source in {self.root}/src")
            typecheck("./src", use_local_packages=args.use_local_packages == "yes")
            pm.done()

    def run_tests(self, args: argparse.Namespace):
        """Discover and execute pytest suites, optionally with coverage collection."""
        if "e" in args.action:
            os.environ["CANARY_RUN_EXAMPLES_TEST"] = "1"

        with working_dir(self.root):
            test_paths = discover_test_paths(Path(self.root))

            if not test_paths:
                raise ValueError("No test paths discovered")

            if "t" in args.action:
                results = run_pytests_parallel(Path(self.root), test_paths)
                failed = [r for r in results if not r.ok]

                if failed:
                    for r in failed:
                        if r.stdout:
                            sys.stdout.write(r.stdout)
                        if r.stderr:
                            sys.stderr.write(r.stderr)

                    raise ValueError(
                        f"{len(failed)} pytest runs failed: {', '.join(r.path for r in failed)}"
                    )

            else:
                pm = logger.progress_monitor(f"Running coverage in {self.root}")
                coverage("run")
                pm.done()

                pm = logger.progress_monitor("Creating coverage report")
                coverage("report")
                coverage("html")
                pm.done()

    def make_docs(self, args: argparse.Namespace):
        """Build Sphinx HTML documentation from ``docs/``."""
        with working_dir(f"{self.root}/docs"):
            logger.info(f"Making documentation in {self.root}/docs")
            make("api-docs")
            make("clean")
            make("html")


def make(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``make`` with the given arguments, raising on non-zero exit."""
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command = ["make", *args]
    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def ruff(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``ruff`` with the given arguments, raising on non-zero exit."""
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command = ["ruff", *args]
    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def ruff_check(*paths: str, **kwargs) -> subprocess.CompletedProcess:
    """Run ``ruff check --fix`` twice (second pass selects S324) on *paths*."""
    ruff("check", "--fix", *paths, **kwargs)
    return ruff("check", "--fix", "--select", "S324", *paths, **kwargs)


def bandit(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``bandit`` with the given arguments, raising on non-zero exit."""
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command = ["bandit", *args]
    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def typecheck(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``ty check`` (preferred) or ``mypy`` with optional extra search paths."""
    use_local_packages: bool = bool(kwargs.pop("use_local_packages", True))

    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command: list[str]

    if ty := shutil.which("ty"):
        command = [ty, "check", *args]

        if use_local_packages:
            d = Path(site.getusersitepackages())
            if d.exists():
                command.insert(2, f"--extra-search-path={d}")

        d = Path(str(ir.files("hpc_connect"))).parent
        if d.name == "src" and d.exists():
            command.insert(2, f"--extra-search-path={d}")

    else:
        command = ["mypy", *args]

    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def pytest(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``pytest`` with the given arguments, raising on non-zero exit."""
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command = ["pytest", *args]
    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def run_pytests_parallel(
    root: Path,
    test_paths: Sequence[str],
    *,
    max_workers: int | None = None,
    pytest_args: tuple[str, ...] = (),
) -> list[PytestResult]:
    """Run pytest concurrently over multiple paths using a process pool."""
    results: list[PytestResult] = []

    with ProcessPoolExecutor(max_workers=max_workers or os.cpu_count()) as ex:
        futures: dict[Future, str] = {}

        for p in test_paths:
            ap = os.path.abspath(p)
            rp = os.path.relpath(ap, root)
            logger.info(f"Submitting tests in ./{rp} to pytest")
            fut = ex.submit(run_pytest_one, str(root), str(p), pytest_args)
            futures[fut] = str(p)

        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            logger.info(f"pytest finished: {res.path} ({res.elapsed_s:.1f}s) rc={res.returncode}")

    return results


def coverage(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``coverage`` with the given arguments, raising on non-zero exit."""
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"

    command = ["coverage", *args]
    cp = subprocess.run(command, **kwargs)

    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)  # ty: ignore[no-matching-overload]
        if cp.stderr:
            sys.stderr.write(cp.stderr)  # ty: ignore[no-matching-overload]
        raise ValueError(f"{' '.join(command)} failed!")

    return cp


def add_licenses(path: str) -> None:
    """Recursively add missing license headers under *path*.

    Skips ``third_party`` and ``TestResults`` trees.
    """
    for dirname, dirs, files in os.walk(path):
        if dirname.endswith(("third_party", "TestResults")):
            del dirs[:]
            continue
        for file in files:
            if file.endswith((".py", ".pyt", ".vvt", ".cmake", ".sh")):
                add_python_license(os.path.join(dirname, file))
            elif file.endswith(".rst"):
                add_rst_license(os.path.join(dirname, file))


def add_python_license(file: str) -> None:
    """Prepend the ``#``-style SPDX license header if absent (after any shebang)."""
    license = (
        "# Copyright NTESS. See COPYRIGHT file for details.\n#\n# SPDX-License-Identifier: MIT\n\n"
    )
    with open(file) as fh:
        content = fh.read()
    if "# Copyright NTESS" in content:
        return
    logger.info(f"Adding license to {file}")
    with open(file, "w") as fh:
        if content.startswith("#!"):
            lines = content.splitlines(keepends=True)
            fh.write(lines[0])
            fh.write(license)
            fh.write("".join(lines[1:]))
        else:
            fh.write(license)
            fh.write(content)


def add_rst_license(file: str) -> None:
    """Prepend the reStructuredText-comment SPDX license header if absent."""
    license = (
        ".. Copyright NTESS. See COPYRIGHT file for details.\n\n   SPDX-License-Identifier: MIT\n\n"
    )
    with open(file) as fh:
        content = fh.read()
    if ".. Copyright NTESS" in content:
        return
    logger.info(f"Adding license to {file}")
    with open(file, "w") as fh:
        fh.write(license)
        fh.write(content)


def update_pyproject_version(root: Path, version: str) -> None:
    """Rewrite the ``version`` field in ``pyproject.toml``'s ``[project]`` table."""
    file = root / "pyproject.toml"

    if not file.exists():
        raise FileNotFoundError(file)

    text = file.read_text()
    lines = text.splitlines(keepends=True)

    project_header_re = re.compile(r"^\s*\[project\]\s*(?:#.*)?$")
    table_header_re = re.compile(r"^\s*\[[^\]]+\]\s*(?:#.*)?$")
    version_re = re.compile(r"""^(\s*version\s*=\s*)(["'])(.*?)(\2)(.*)$""")

    in_project = False
    saw_project = False
    replaced = False
    old_version: str | None = None

    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]

        if project_header_re.match(body):
            in_project = True
            saw_project = True
            continue

        if in_project and table_header_re.match(body):
            break

        if not in_project:
            continue

        if match := version_re.match(body):
            old_version = match.group(3)
            quote = match.group(2)
            lines[i] = f"{match.group(1)}{quote}{version}{quote}{match.group(5)}{ending}"
            replaced = True
            break

    if not saw_project:
        raise ValueError(f"{file}: missing [project] table")

    if not replaced:
        raise ValueError(f"{file}: missing project.version")

    file.write_text("".join(lines))
    logger.info(f"[bold]Updated[/] pyproject.toml version: {old_version} -> {version}")


def discover_test_paths(root: Path) -> tuple[str, ...]:
    """Return pytest paths for Canary core plus registered Canary extensions."""
    import importlib.metadata as importlib_metadata
    import importlib.resources as importlib_resources

    from _canary.hookspec import project_name

    root = root.resolve()

    paths: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if not path.is_dir():
            return

        resolved = path.resolve()
        key = str(resolved)

        if key in seen:
            return

        seen.add(key)
        try:
            p = resolved.relative_to(root).as_posix()
        except ValueError:
            p = str(resolved)
        paths.append(p)

    # Core repository tests are not an entry-point package.
    add(root / "tests")

    # In-tree extensions via the old candidate mechanism.
    for name, module in canary_entry_point_modules(root).items():
        for path in entry_point_test_candidates(root, module):
            if path.is_dir():
                add(path)

    # Out-of-tree extensions: use importlib.resources + .canary-ext-tests marker.
    for ep in importlib_metadata.entry_points(group=project_name):
        try:
            pkg_name = ep.value.split(".")[0]
            pkg_files = importlib_resources.files(pkg_name)
        except (ModuleNotFoundError, TypeError, ValueError):
            continue

        try:
            tests_path = pkg_files.joinpath("tests")
            marker = tests_path.joinpath(".canary-ext-tests")
            if not marker.is_file():
                continue
        except (TypeError, FileNotFoundError, NotADirectoryError):
            continue

        try:
            real_tests = Path(str(tests_path))
            add(real_tests)
        except Exception as exc:
            logger.debug("Could not add tests for %s: %s", ep.name, exc)

    # In-repo sub-packages: add tests from packages/ subdirectories when present.
    for pkg_dir in sorted((root / "packages").iterdir()) if (root / "packages").is_dir() else []:
        add(pkg_dir / "tests")

    logger.info("[bold]Discovered[/] %d pytest path(s): %s", len(paths), ", ".join(paths))
    return tuple(paths)


def canary_entry_point_modules(root: Path) -> dict[str, str]:
    """Return ``{entry_point_name: module}`` for the ``canary`` entry-point group."""
    import importlib.metadata as importlib_metadata

    from _canary.hookspec import project_name

    modules: dict[str, str] = {}

    for ep in importlib_metadata.entry_points(group=project_name):
        if ep.module:
            modules[str(ep.name)] = ep.module

    return modules


def entry_point_test_candidates(root: Path, module: str) -> tuple[Path, ...]:
    """Return candidate test directory paths for a canary entry-point module."""
    parts = module.split(".")
    top_package = parts[0]

    return (root / "src" / top_package / "tests", root / "src" / Path(*parts) / "tests")
