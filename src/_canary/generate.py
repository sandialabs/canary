# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Canary Generate Pipeline
========================

This module implements the generateion lifecycle for converting generator output into fully resolved
test specs. The central orchestrator is the ``Generator`` object, which progresses through
validation, resolution, and finally hook-driven post-processing.

The ``canary_generate(generator)`` function coordinates the entire process using Pluggy hooks.  Plugins
may observe or modify the generate at specific stages.

Flow Diagram
------------

The following diagram illustrates the full lifecycle::

  Generator(s)
    Produces [Un]resolved test specs
                      ↓
  Generator(generators)
    Generate JobSpecIR from generator outputs
                      ↓
  canary_generate(generators)
  • pluginmanager.hook.canary_generatestart()
  • generator.run()
    • validate(...)
    • resolve(...)
  • pluginmanager.hook.canary_generate_modifiyitems()
  • pluginmanager.hook.canary_generate_report()
  → generator.resolved_specs()

"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

import rich.box
from rich.console import Console
from rich.table import Table

from . import config
from .hookspec import hookimpl
from .resolve_dependency import resolve
from .util import logging
from .util.multiprocessing import starmap
from .util.string import pluralize

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .generator import AbstractTestGenerator
    from .ir import JobSpecIR
    from .jobspec import JobSpec


logger = logging.get_logger(__name__)


class Generator:
    def __init__(
        self,
        generators: list["AbstractTestGenerator"],
        workspace: Path,
        on_options: Iterable[str] = (),
    ) -> None:
        self.generators = generators
        self.workspace = workspace
        self.on_options = list(on_options)
        self.specs: list["JobSpec"] = []
        self.ready: bool = False

    def run(self) -> list["JobSpec"]:
        pm = logger.progress_monitor("[bold]Generating[/] test specs from generators")
        config.pluginmanager.hook.canary_generatestart(generator=self)
        irs: list["JobSpecIR | JobSpec"] = generate_jobspecs(self.generators, self.on_options)
        pm.done()
        self.validate(irs)
        pm = logger.progress_monitor("[bold]Resolving[/] test spec dependencies")
        self.specs = resolve(irs)
        self.ready = True
        pm.done()
        config.pluginmanager.hook.canary_generate_modifyitems(generator=self)
        config.pluginmanager.hook.canary_generate_report(generator=self)
        return self.specs

    def validate(self, specs: list["JobSpecIR | JobSpec"]) -> None:
        pm = logger.progress_monitor("[bold]Searching[/] for duplicated tests")
        ids = [spec.id for spec in specs]
        counts: dict[str, int] = {}
        for id in ids:
            counts[id] = counts.get(id, 0) + 1
        duplicate_ids = {id for id, count in counts.items() if count > 1}
        duplicates: dict[str, list["JobSpecIR | JobSpec"]] = {}
        # if there are duplicates, we are in error condition and lookup cost is not important
        for id in duplicate_ids:
            duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
        if duplicates:
            logger.error("Duplicate test IDs generated for the following test cases")
            for id, dspecs in duplicates.items():
                logger.error(f"{id}:")
                for spec in dspecs:
                    logger.log(
                        logging.EMIT,
                        f"  - {spec.display_name()}: {spec.file_path}",
                        extra={"prefix": ""},
                    )
            raise ValueError("Duplicate test IDs in test suite")
        pm.done()
        return None

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        group = parser.add_argument_group("test spec generation")
        group.add_argument(
            "-o",
            dest="on_options",
            default=None,
            metavar="option",
            action="append",
            help="Turn option(s) on, such as '-o dbg' or '-o intel'",
        )


@hookimpl
def canary_generate_report(generator: Generator) -> None:
    nc, ng = len(generator.specs), len(generator.generators)
    logger.info("[bold]Generated[/] %d test specs from %d generators" % (nc, ng))
    excluded = [spec for spec in generator.specs if spec.mask]
    if excluded:
        n = len(excluded)
        logger.info("[bold]Excluded[/] %d test %s during generation" % (n, pluralize("spec", n)))
        table = Table(show_header=True, header_style="bold", box=rich.box.SIMPLE_HEAD)
        table.add_column("Reason", no_wrap=True)
        table.add_column("Count", justify="right")
        reasons: dict[str | None, list["JobSpec"]] = {}
        for spec in excluded:
            reasons.setdefault(spec.mask.reason, []).append(spec)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            table.add_row(reason, str(len(reasons[key])))
        console = Console(file=sys.stderr)
        console.print(table)


def generate_from_one(
    file: "AbstractTestGenerator", on_options: list[str] | None
) -> list["JobSpecIR | JobSpec"]:
    return list(file.lock(on_options=on_options))


def generate_jobspecs(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["JobSpecIR | JobSpec"]:
    if config.get("debug"):
        return generate_jobspecs_serial(generators, on_options)
    return generate_jobspecs_parallel(generators, on_options)


def generate_jobspecs_parallel(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["JobSpecIR | JobSpec"]:
    # In testing
    locked = starmap(
        generate_from_one,
        [(f, on_options) for f in generators],
        initializer=worker_init,
        initargs=(config.snapshot(),),
    )
    return [spec for group in locked for spec in group]


def worker_init(snapshot: dict[str, Any]):
    config.load_snapshot(snapshot)


def generate_jobspecs_serial(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["JobSpecIR | JobSpec"]:
    specs: list["JobSpecIR | JobSpec"] = []
    for f in generators:
        specs.extend(generate_from_one(f, on_options))
    return specs
