from ... import config
from ...testcase import TestCase
from ..hookspec import hookimpl


@hookimpl(trylast=True)
def canary_resource_requirements_satisfiable(case: TestCase) -> bool:
    """determine if the resources for this test are satisfiable"""
    return config.resource_pool.satisfiable(case.required_resources())


@hookimpl(trylast=True)
def canary_resource_count_per_node(resource: str) -> int:
    """determine if the resources for this test are satisfiable"""
    return config.get(f"machine:{resource}_per_node") or 0
