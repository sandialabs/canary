# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import datetime
import importlib.resources as ir
import os
import re
import shutil
import site
import subprocess
import sys
import time
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from ..hookspec import hookimpl
from ..util import logging
from ..util.filesystem import working_dir
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Check())


stdout: Any = subprocess.PIPE
stderr: Any = subprocess.PIPE

logger = logging.get_logger(__name__)


class Action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        action = getattr(namespace, "action", set())
        assert option_string is not None
        value = option_string[1:]
        action.add(value)
        namespace.action = action


class Check(CanarySubcommand):
    name = "check"
    description = "Run canary's internal checks"
    add_help = False
    aliases = ["pre-commit"]

    def setup_parser(self, parser: "Parser") -> None:
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
        parser.add_argument(
            "-v",
            nargs=0,
            action=Action,
            help="update pyproject.toml project.version to today's YY.MM.DD value",
        )
        parser.add_argument("--verbose", action="store_true", help="verbose")
        parser.add_argument(
            "--local-packages",
            choices=("yes", "no"),
            default="no" if "VIRTUAL_ENV" in os.environ else "yes",
            dest="use_local_packages",
            help="Add local site-packages to search path when running type checker",
        )
        parser.add_argument(
            "--release-version",
            action="store_true",
            help="When used with -v, stamp a release version without .dev0",
        )

    def execute(self, args: argparse.Namespace) -> int:
        global stdout
        global stderr

        if args.verbose:
            stdout = sys.stdout
            stderr = sys.stderr

        root = ir.files("canary").joinpath("../..")
        if not root.joinpath(".git").is_dir():
            raise ValueError("canary check must be run from a editable install of canary")

        self.root = os.path.normpath(str(root))

        if not hasattr(args, "action"):
            args.action = set("fcmbt")

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

        if "v" in args.action:
            self.stamp_version(args)

        logger.info("All checks complete!")

        return 0

    def stamp_version(self, args: argparse.Namespace) -> None:
        today = datetime.date.today()
        version = f"{today.year % 100}.{today.month}.{today.day}"
        if not args.release_version:
            version = f"{version}.dev0"
        update_pyproject_version(Path(self.root), version)

    @staticmethod
    def find_pyt_files(top: str) -> list[str]:
        pyt_files: list[str] = []

        for dirname, _, files in os.walk(top):
            pyt_files.extend([os.path.join(dirname, f) for f in files if f.endswith(".pyt")])

        return pyt_files

    def format_code(self, args: argparse.Namespace):
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

    def lint_check_code(self, args: argparse.Namespace):
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

    def security_check(self, args: argparse.Namespace):
        with working_dir(self.root):
            pm = logger.progress_monitor("Checking source for security violations")
            bandit("-c", "./pyproject.toml", "-r", "src/")
            pm.done()

    def type_check_code(self, args: argparse.Namespace):
        with working_dir(self.root):
            pm = logger.progress_monitor(f"Type checking source in {self.root}/src")
            typecheck("./src", use_local_packages=args.use_local_packages == "yes")
            pm.done()

    def run_tests(self, args: argparse.Namespace):
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
        with working_dir(f"{self.root}/docs"):
            logger.info(f"Making documentation in {self.root}/docs")
            make("api-docs")
            make("clean")
            make("html")


def make(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
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
    ruff("check", "--fix", *paths, **kwargs)
    return ruff("check", "--fix", "--select", "S324", *paths, **kwargs)


def bandit(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
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


@dataclass(frozen=True)
class PytestResult:
    path: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_pytest_one(root: str, relpath: str, pytest_args: tuple[str, ...] = ()) -> PytestResult:
    # Runs in a worker process
    t0 = time.time()
    command = ["pytest", relpath, *pytest_args]
    cp = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, encoding="utf-8")

    return PytestResult(
        path=relpath,
        returncode=cp.returncode,
        stdout=cp.stdout or "",
        stderr=cp.stderr or "",
        elapsed_s=time.time() - t0,
    )


def run_pytests_parallel(
    root: Path,
    test_paths: Sequence[str],
    *,
    max_workers: int | None = None,
    pytest_args: tuple[str, ...] = (),
) -> list[PytestResult]:
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

            # Print on completion (no interleaving during run)
            logger.info(f"pytest finished: {res.path} ({res.elapsed_s:.1f}s) rc={res.returncode}")

    return results


def coverage(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
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


def update_pyproject_version(root: Path, version: str) -> None:
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
    """Return pytest paths for Canary core plus registered Canary extensions.

    The repository-level ``tests`` directory is currently special-cased.
    Extension test directories are discovered from
    ``[project.entry-points."canary"]`` in pyproject.toml.
    """
    root = root.resolve()

    paths: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if not path.is_dir():
            return

        rel = path.resolve().relative_to(root).as_posix()

        if rel in seen:
            return

        seen.add(rel)
        paths.append(rel)

    # Core repository tests are not an entry-point package.
    add(root / "tests")

    for name, module in canary_entry_point_modules(root).items():
        found = False

        for path in entry_point_test_candidates(root, module):
            if path.is_dir():
                add(path)
                found = True

        if not found:
            logger.debug("No tests directory found for canary entry point %s=%s", name, module)

    logger.info("[bold]Discovered[/] %d pytest path(s): %s", len(paths), ", ".join(paths))
    return tuple(paths)


def canary_entry_point_modules(root: Path) -> dict[str, str]:
    """Return ``{entry_point_name: module}`` for the ``canary`` entry-point group.

    Uses the installed package metadata (the same mechanism the plugin manager
    uses to discover plugins) rather than parsing ``pyproject.toml``.  This
    reflects what is actually installed and avoids a hard dependency on
    ``tomllib`` (Python 3.11+).
    """
    import importlib.metadata as importlib_metadata

    from ..hookspec import project_name

    modules: dict[str, str] = {}

    for ep in importlib_metadata.entry_points(group=project_name):
        # ``EntryPoint.module`` strips any ``:object`` attribute and extras.
        if ep.module:
            modules[str(ep.name)] = ep.module

    return modules


def entry_point_test_candidates(root: Path, module: str) -> tuple[Path, ...]:
    parts = module.split(".")
    top_package = parts[0]

    return (root / "src" / top_package / "tests", root / "src" / Path(*parts) / "tests")
