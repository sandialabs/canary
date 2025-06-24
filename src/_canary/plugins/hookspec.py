# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Type

import pluggy

from .types import CanaryReporter
from .types import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..config.config import Config
    from ..generator import AbstractTestGenerator
    from ..session import Session
    from ..test.batch import TestBatch
    from ..test.case import TestCase

project_name = "canary"
hookspec = pluggy.HookspecMarker(project_name)
hookimpl = pluggy.HookimplMarker(project_name)


@hookspec
def canary_testcase_generator() -> Type["AbstractTestGenerator"]:
    """Returns an implementation of AbstractTestGenerator"""
    raise NotImplementedError


@hookspec
def canary_addoption(parser: "Parser") -> None:
    """Register new command line options or modify existing ones."""


@hookspec
def canary_configure(config: "Config") -> None:
    """Perform custom configuration of the test environment"""


@hookspec
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


@hookspec
def canary_session_start(session: "Session") -> None:
    """Called after the session object has been created and before performing collection and
    entering the run test loop."""


@hookspec
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    """Called after the test session has finished allowing plugins to perform custom actions after
    all tests have been run."""


@hookspec(firstresult=True)
def canary_runtests(cases: list["TestCase"], fail_fast: bool) -> int:
    raise NotImplementedError


@hookspec
def canary_runtests_summary(cases: list["TestCase"], include_pass: bool, truncate: int) -> None: ...


@hookspec
def canary_session_reporter() -> CanaryReporter:
    """Register Canary report type"""
    raise NotImplementedError


@hookspec
def canary_statusreport(session: "Session") -> None:
    pass


@hookspec
def canary_collectreport(cases: list["TestCase"]) -> None:
    pass


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
) -> None:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """


@hookspec(firstresult=True)
def canary_testcases_batch(cases: list["TestCase"]) -> list["TestBatch"] | None:
    """Batch test cases"""


@hookspec
def canary_testcase_modify(case: "TestCase") -> None:
    """Modify the test case before the test run."""


@hookspec
def canary_testcase_setup(case: "TestCase") -> None:
    """Called to perform the setup phase for a test case.

    The default implementation runs ``case.setup()``.

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """


@hookspec(firstresult=True)
def canary_testcase_run(case: "TestCase", qsize: int, qrank: int) -> None:
    """Called to run the test case

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """


@hookspec
def canary_testcase_finish(case: "TestCase") -> None:
    """Called to perform the finishing tasks for the test case

    The default implementation runs ``case.finish()``

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """


@hookspec
def canary_testbatch_setup(batch: "TestBatch") -> None:
    """Called to perform the setup phase for a batch of test cases.

    The default implementation runs ``batch.setup()``.

    Args:
        The test case batch.

    """


@hookspec(firstresult=True)
def canary_testbatch_run(batch: "TestBatch", qsize: int, qrank: int) -> None:
    """Called to run the test case batch

    Args:
        The test case batch.

    """


@hookspec
def canary_testbatch_finish(batch: "TestBatch") -> None:
    """Called to perform the finishing tasks for the test case batch

    The default implementation runs ``batch.finish()``

    Args:
        The test case.

    """
