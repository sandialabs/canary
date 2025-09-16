from ... import config
from ...testcase import TestCase
from ..hookspec import hookimpl


@hookimpl(trylast=True)
def canary_resource_requirements_satisfiable(case: TestCase) -> bool:
    """determine if the resources for this test are satisfiable"""
    return config.resource_pool.satisfiable(case.required_resources())
