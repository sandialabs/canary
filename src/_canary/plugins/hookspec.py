# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# mypy: disable-error-code=empty-body

from typing import TYPE_CHECKING
from typing import Any
from typing import Type

import pluggy

from .types import CanaryReporter
from .types import CanarySubcommand

if TYPE_CHECKING:
    from ..atc import AbstractTestCase
    from ..config.argparsing import Parser
    from ..config.config import Config as CanaryConfig
    from ..generator import AbstractTestGenerator
    from ..session import Session
    from ..testcase import TestCase
    from .manager import CanaryPluginManager
    from .types import Result

project_name = "canary"
hookspec = pluggy.HookspecMarker(project_name)
hookimpl = pluggy.HookimplMarker(project_name)


@hookspec(firstresult=True)
def canary_testcase_generator(
    root: str, path: str | None
) -> "AbstractTestGenerator | Type[AbstractTestGenerator]":
    """Returns an implementation of AbstractTestGenerator"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_generator(root: str, path: str | None) -> "AbstractTestGenerator":
    """Returns an implementation of AbstractTestGenerator"""
    raise NotImplementedError


@hookspec
def canary_addoption(parser: "Parser") -> None:
    """Register new command line options or modify existing ones."""


@hookspec
def canary_addcommand(parser: "Parser") -> None:
    """Add a subcommand to Canary

    Example:

    .. code-block:: python

       import argparse

       from canary import plugins

       class MyCommand(CanarySubcommand):
           name = "my-command"
           description = "my-command description"

           def setup_parser(parser: canary.Parser) -> None:
               parser.add_argument("--flag")

           def execute(args: argparse.Namespace) -> int:
               ...

       @plugins.hookimpl
       def canary_addcommand(parser: canary.Parser):
           parser.add_command(MyCommand())

    """


@hookspec
def canary_subcommand() -> CanarySubcommand:
    raise NotImplementedError


@hookspec
def canary_configure(config: "CanaryConfig") -> None:
    """Perform custom configuration of the test environment"""


@hookspec
def canary_session_startup(session: "Session") -> None:
    """Called after the session object has been created and before performing collection and
    entering the run test loop."""


_impl_warning = "canary_session_start is deprecated and will be removed, use canary_session_startup"


@hookspec(warn_on_impl=DeprecationWarning(_impl_warning))
def canary_session_start(session: "Session") -> None:
    raise NotImplementedError


@hookspec
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    """Called after the test session has finished allowing plugins to perform custom actions after
    all tests have been run."""
    raise NotImplementedError


@hookspec
def canary_runtests_startup() -> None:
    """Called at the beginning of `canary run`"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtests(cases: list["TestCase"]) -> int:
    raise NotImplementedError


@hookspec
def canary_runtests_summary(cases: list["TestCase"], include_pass: bool, truncate: int) -> None:
    raise NotImplementedError


@hookspec
def canary_session_reporter() -> CanaryReporter:
    """Register Canary report type"""
    raise NotImplementedError


@hookspec
def canary_statusreport(session: "Session") -> None:
    raise NotImplementedError


@hookspec
def canary_collectreport(cases: list["TestCase"]) -> None:
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_discover_generators(
    root: str, paths: list[str] | None
) -> tuple[list["AbstractTestGenerator"], int]:
    """Discover test cases in root

    Args:
      root: Search directory or path to single test file
      paths: Test file paths relative to root

    Returns:
      list[AbstractTestGenerator]: list of generators found
      int: number of parsing errors encountered

    Notes:
      - If ``root`` is the path to a file then ``paths`` will be ``None`` and a single test
        generator will be returned.
      - If ``paths`` is ``None``, then ``root`` should be searched recursively for any test
        generators
      - Otherwise, each ``path`` in ``paths`` is a file relative to ``root`` representing a test
        generator

    """
    raise NotImplementedError


@hookspec
def canary_testsuite_mask(
    cases: list["TestCase"],
    keyword_exprs: list[str],
    parameter_expr: str,
    owners: set[str],
    regex: str | None,
    case_specs: list[str] | None,
    start: str | None,
    ignore_dependencies: bool,
) -> None:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """


@hookspec
def canary_testcase_modify(case: "TestCase") -> None:
    """Modify the test case before the test run."""


@hookspec(firstresult=True)
def canary_testcase_setup(case: "AbstractTestCase") -> bool:
    """Called to perform the setup phase for a test case.

    The default implementation runs ``case.setup()``.

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_run(case: "AbstractTestCase", qsize: int, qrank: int) -> bool:
    """Called to run the test case

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_finish(case: "AbstractTestCase") -> bool:
    """Called to perform the finishing tasks for the test case

    The default implementation runs ``case.finish()``

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec
def canary_addhooks(pluginmanager: "CanaryPluginManager") -> None:
    "Called at plugin registration time to add new hooks"
    raise NotImplementedError


@hookspec
def canary_resource_pool_fill(config: "CanaryConfig", pool: dict[str, dict[str, Any]]) -> None:
    """Fill ``resources`` with available resources."""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_resource_pool_accommodates(case: "TestCase") -> "Result":
    """Determine if there are sufficient resource to run ``case``."""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_resource_pool_count(type: str) -> int:
    """Return the number resources available of type ``type``"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_resource_pool_types() -> list[str]:
    """Return the names of available resources"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_resource_pool_describe() -> str:
    """Return a string describing the resource pool"""
    raise NotImplementedError
