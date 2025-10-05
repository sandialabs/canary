from typing import TYPE_CHECKING

from ... import config
from ..hookspec import hookimpl
from ..types import Result

if TYPE_CHECKING:
    from ...testcase import TestCase


@hookimpl(trylast=True)
def canary_resources_avail(case: "TestCase") -> Result:
    return config.resource_pool.accommodates(case)


@hookimpl(trylast=True)
def canary_resource_count(type: "str") -> int:
    return config.resource_pool.count(type)


@hookimpl(trylast=True)
def canary_resource_types() -> list[str]:
    return config.resource_pool.types
