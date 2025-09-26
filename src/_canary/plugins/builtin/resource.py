from typing import TYPE_CHECKING

from ... import config
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...testcase import TestCase


@hookimpl(trylast=True)
def canary_resource_satisfiable(case: "TestCase") -> bool:
    return config.resource_pool.satisfiable(case.required_resources())


@hookimpl(trylast=True)
def canary_resource_count(type: "str") -> int:
    return config.resource_pool.count(type)


@hookimpl(trylast=True)
def canary_resource_types() -> list[str]:
    return config.resource_pool.types
