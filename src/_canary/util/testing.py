# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

from .graph import static_order

if TYPE_CHECKING:
    from ..testcase import TestCase
    from ..testspec import ResolvedSpec


class CanaryCommand:
    def __init__(self, command_name: str) -> None:
        self.command_name = command_name
        self.default_args: list[str] = []

    def add_default_args(self, *args: str) -> None:
        self.default_args.extend(args)

    def __call__(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess:
        env: dict[str, str] = {}
        if "env" in kwargs:
            env.update(kwargs.pop("env"))
        else:
            env.update(os.environ)
        env.pop("CANARYCFG64", None)
        env["CANARY_DISABLE_KB"] = "1"

        cpus: int = -1
        if "cpus" in kwargs:
            cpus = int(kwargs.pop("cpus"))
        if "_CANARY_TESTING_CPUS" in env:
            # Environment variable takes precedence
            cpus = int(env.pop("_CANARY_TESTING_CPUS"))

        gpus: int = -1
        if "gpus" in kwargs:
            gpus = int(kwargs.pop("gpus"))
        if "_CANARY_TESTING_GPUS" in env:
            # Environment variable takes precedence
            gpus = int(env.pop("_CANARY_TESTING_GPUS"))

        cmd: list[str] = [sys.executable, "-m", "canary"]
        if kwargs.pop("debug", False):
            cmd.append("-d")
        if cpus > 0:
            cmd.extend(["-c", f"resource_pool:cpus:{cpus}"])
        if gpus > 0:
            cmd.extend(["-c", f"resource_pool:gpus:{gpus}"])
        cmd.extend(self.default_args)
        cmd.append(self.command_name)
        cmd.extend(args)
        cp = subprocess.run(cmd, **kwargs)
        return cp


def generate_random_testcases(
    root: Path,
    count: int = 10,
    max_params: int = 3,
    max_rows: int = 5,
) -> list["TestCase"]:
    from ..testcase import TestCase
    from ..testexec import ExecutionSpace

    session = root / "session"
    lookup: dict[str, TestCase] = {}
    cases: list[TestCase] = []
    specs = generate_random_testspecs(
        root=root, count=count, max_params=max_params, max_rows=max_rows
    )
    for spec in static_order(specs):
        dependencies = [lookup[dep.id] for dep in spec.dependencies]
        case: TestCase
        space = ExecutionSpace(root=session, path=Path(spec.execpath), session=session.name)
        case = TestCase(spec=spec, workspace=space, dependencies=dependencies)
        lookup[spec.id] = case
        cases.append(case)
    return cases


def generate_random_testspecs(
    root: Path,
    count: int = 10,
    max_params: int = 3,
    max_rows: int = 5,
) -> list["ResolvedSpec"]:
    from ..collect import Collector
    from ..generate import Generator

    generate_random_test_files(
        root / "tests", count=count, max_params=max_params, max_rows=max_rows
    )
    collector = Collector()
    collector.add_scanpath((root / "tests").as_posix(), [])
    generators = collector.run()
    print(generators)
    generator = Generator(generators, workspace=root, on_options=[])
    specs = generator.run()
    print(specs)
    return specs


def generate_random_test_files(
    root: Path,
    count: int = 10,
    max_params: int = 3,
    max_rows: int = 5,
    with_deps: bool = True,
) -> None:
    """Generate a random Canary test suite for performance testing."""

    PARAM_NAMES: list[str] = ["a", "b", "c", "x", "y", "z"]
    KEYWORDS: list[str] = ["fast", "long", "spam", "eggs", "ham"]

    def chunked(seq: list[str], size: int) -> Iterable[list[str]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    root.mkdir(parents=True, exist_ok=True)
    filenames: list[str] = []
    for i in range(count):
        name = f"test_{i:06d}.pyt"
        filenames.append(name)

    cache: list[str] = []
    for group in chunked(filenames, 1_000):
        for fname in group:
            name = Path(fname).stem

            num_params = random.randint(1, max_params)
            num_rows = random.randint(1, max_rows)

            names = sorted(random.sample(PARAM_NAMES, num_params))
            params = {n: list(range(num_rows)) for n in names}

            kws = random.sample(KEYWORDS, random.randint(0, 3))
            deps = []
            if cache and random.random() < 0.2:
                dep = cache.pop(0)
                deps = [dep]

            cache.append(name)
            fp = io.StringIO()
            fp.write("#/usr/bin/env python3\n")
            fp.write("import canary\n")
            if kws:
                fp.write(f"canary.directives.keywords({', '.join(repr(kw) for kw in kws)})\n")
            if params:
                p_names = ",".join(params.keys())
                p_values = list(zip(*params.values()))
                fp.write(f"canary.directives.parameterize('{p_names}', {p_values})\n")
                cache.extend(generate_spec_names(name, p_names, p_values))

            if deps:
                fp.write("\n".join(f"canary.directives.depends_on({dep!r})" for dep in deps))

            (root / fname).write_text(fp.getvalue())


def generate_spec_names(family: str, names: str, values: list[tuple[Any, ...]]) -> list[str]:
    param_names = [n.strip() for n in names.split(",")]
    if any(len(param_names) != len(v) for v in values):
        raise ValueError("Incorrect param name/value shape")
    names: list[str] = []
    for value in values:
        parts = [f"{name}={v}" for name, v in zip(param_names, value)]
        name = f"{family}.{'.'.join(sorted(parts))}"
        names.append(name)
    return names
