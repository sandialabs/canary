# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING

from ... import config
from ...testspec import resolve as resolve_specs
from ...util import logging
from ...util.parallel import starmap
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...generator import AbstractTestGenerator
    from ...testspec import DraftSpec
    from ...testspec import ResolvedSpec


logger = logging.get_logger(__name__)


@hookimpl
def canary_generate(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["ResolvedSpec"]:
    """Generate (lock) test specs from generators

    Args:
        generators: Test case generators

    Returns:
        A list of test specs

    """
    pm = logger.progress_monitor("@*{Generating} test specs")
    locked: list[list["DraftSpec"]] = []
    if config.get("debug"):
        for f in generators:
            locked.append(lock_file(f, on_options))
    else:
        locked.extend(starmap(lock_file, [(f, on_options) for f in generators]))
    drafts: list["DraftSpec"] = []
    for group in locked:
        for spec in group:
            drafts.append(spec)
    pm.done()

    duplicates = find_duplicates(drafts)
    if duplicates:
        logger.error("Duplicate test IDs generated for the following test cases")
        for id, dspecs in duplicates.items():
            logger.error(f"{id}:")
            for spec in dspecs:
                logger.log(
                    logging.EMIT,
                    f"  - {spec.display_name}: {spec.file_path}",
                    extra={"prefix": ""},
                )
        raise ValueError("Duplicate test IDs in test suite")

    pm = logger.progress_monitor("@*{Resolving} test spec dependencies")
    specs = resolve_specs(drafts)
    pm.done()

    nc, ng = len(specs), len(generators)
    logger.info("@*{Generated} %d test specs from %d generators" % (nc, ng))
    return specs


def lock_file(file: "AbstractTestGenerator", on_options: list[str] | None):
    return file.lock(on_options=on_options)


def find_duplicates(specs: list["DraftSpec"]) -> dict[str, list["DraftSpec"]]:
    pm = logger.progress_monitor("@*{Searching} for duplicated tests")
    ids = [spec.id for spec in specs]
    counts: dict[str, int] = {}
    for id in ids:
        counts[id] = counts.get(id, 0) + 1

    duplicate_ids = {id for id, count in counts.items() if count > 1}
    duplicates: dict[str, list["DraftSpec"]] = {}

    # if there are duplicates, we are in error condition and lookup cost is not important
    for id in duplicate_ids:
        duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
    pm.done()
    return duplicates
