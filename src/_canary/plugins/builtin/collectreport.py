from ...test.case import TestCase
from ...third_party.color import colorize
from ...util import glyphs
from ...util import logging
from ...util.string import pluralize
from ..hookspec import hookimpl


@hookimpl
def canary_collectreport(cases: list[TestCase]) -> None:
    excluded: list[TestCase] = []
    for case in cases:
        if case.wont_run():
            excluded.append(case)
    n = len(cases) - len(excluded)
    logging.info(colorize("@*{Selected} %d test %s" % (n, pluralize("case", n))))
    if excluded:
        n = len(excluded)
        logging.info(colorize("@*{Excluding} %d test cases for the following reasons:" % n))
        reasons: dict[str | None, int] = {}
        for case in excluded:
            if case.status.satisfies(("masked", "invalid")):
                reasons[case.status.details] = reasons.get(case.status.details, 0) + 1
        keys = sorted(reasons, key=lambda x: reasons[x])
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            logging.emit(f"{3 * glyphs.bullet} {reasons[key]}: {reason}\n")
