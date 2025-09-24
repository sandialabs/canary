from typing import Generator

from ... import config
from ...testcase import TestCase
from ..hookspec import hookimpl


@hookimpl(trylast=True)
def canary_resource_requirements_satisfiable(case: TestCase) -> bool:
    """determine if the resources for this test are satisfiable"""
    return config.resource_pool.satisfiable(case.required_resources())


@hookimpl(trylast=True)
def canary_resource_count_per_node(type: str) -> int:
    """determine if the resources for this test are satisfiable"""
    return config.resource_pool.count(type)


@hookimpl(wrapper=True, tryfirst=True)
def canary_resource_types() -> Generator[None, list[str], list[str]]:
    types: set[str] = {"cpus", "gpus"}
    result = yield
    for item in result:
        if item is not None:
            types.update(item)
            break
    else:
        types.update(config.resource_pool.types)
    return sorted(types)
