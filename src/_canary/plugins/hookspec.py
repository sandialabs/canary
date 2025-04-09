# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Type

import pluggy

from .types import CanaryReport
from .types import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..config.config import Config
    from ..generator import AbstractTestGenerator
    from ..session import Session
    from ..test.batch import TestBatch
    from ..test.case import TestCase

project_name = "canary"
_hookspec = pluggy.HookspecMarker(project_name)
hookimpl = pluggy.HookimplMarker(project_name)


@_hookspec
def canary_testcase_generator() -> Type["AbstractTestGenerator"]:
    """Returns an implementation of AbstractTestGenerator"""
    raise NotImplementedError


@_hookspec
def canary_addoption(parser: "Parser") -> None:
    """Register new command line options or modify existing ones."""


@_hookspec
def canary_configure(config: "Config") -> None:
    """Perform custom configuration of the test environment"""


@_hookspec
def canary_subcommand() -> CanarySubcommand:
    """Register Canary subcommands

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
       def canary_subcommand():
           return MyCommand()

    """
    raise NotImplementedError


@_hookspec
def canary_session_start(session: "Session") -> None:
    """Called after the session object has been created and before performing collection and
    entering the run test loop."""


@_hookspec
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    """Called after the test session has finished allowing plugins to perform custom actions after
    all tests have been run."""


@_hookspec
def canary_session_report() -> CanaryReport:
    """Register Canary report type"""
    raise NotImplementedError


@_hookspec
def canary_testsuite_mask(
    cases: list["TestCase"],
    keyword_exprs: list[str],
    parameter_expr: str,
    owners: set[str],
    regex: str | None,
    case_specs: list[str] | None,
    start: str | None,
) -> None:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """


@_hookspec(firstresult=True)
def canary_testcases_batch(cases: list["TestCase"]) -> list["TestBatch"] | None:
    pass


@_hookspec
def canary_testcase_modify(case: "TestCase", stage: str = "run") -> None:
    """Modify the test case before the test run."""


@_hookspec
def canary_testcase_setup(case: "TestCase", stage: str = "run") -> None:
    """Called after the test case's working directory has been setup"""


@_hookspec
def canary_testcase_teardown(case: "TestCase", stage: str = "run") -> None:
    """Call user plugin after the test has ran"""
