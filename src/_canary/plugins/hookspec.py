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
    from multiprocessing import Queue

    from ..config.argparsing import Parser
    from ..config.config import Config as CanaryConfig
    from ..generator import AbstractTestGenerator
    from ..testcase import TestCase
    from ..testexec import ExecutionPolicy
    from ..testspec import ResolvedSpec
    from ..testspec import TestSpec
    from ..workspace import Session
    from .manager import CanaryPluginManager
    from .types import Result
    from .types import ScanPath


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


@hookspec(firstresult=True)
def canary_generate(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["ResolvedSpec"]:
    raise NotImplementedError


@hookspec
def canary_generate_modifyitems(specs: list["ResolvedSpec"]) -> None: ...


@hookspec
def canary_generate_report(specs: list["ResolvedSpec"]) -> None: ...


@hookspec
def canary_testcase_modify(case: "TestCase") -> None:
    """Modify the test case before the test run."""


@hookspec(firstresult=True)
def canary_testcase_execution_policy(case: "TestCase") -> "ExecutionPolicy":
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_setup(case: "TestCase") -> bool:
    """Called to perform the setup phase for a test case.

    The default implementation runs ``case.setup()``.

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_run(case: "TestCase", queue: "Queue") -> bool:
    """Called to run the test case

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_finish(case: "TestCase") -> bool:
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


@hookspec(firstresult=True)
def canary_collect_generators(scan_path: "ScanPath") -> list["AbstractTestGenerator"]:
    raise NotImplementedError


@hookspec
def canary_collect_file_patterns() -> list[str]:
    """Return a list of patterns to consider as potential generators"""
    raise NotImplementedError


@hookspec
def canary_collect_modifyitems(files: list[str]) -> None:
    """Filter tests we don't want to generate"""
    raise NotImplementedError


@hookspec
def canary_collect_skip_dirs() -> list[str]:
    """Return a list of directory names to skip when searching for tests"""
    raise NotImplementedError


@hookspec
def canary_select(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: list[str] | None,
    regex: str | None,
    prefixes: list[str] | None,
    ids: list[str] | None,
) -> None:
    raise NotImplementedError


@hookspec
def canary_select_modifyitems(specs: list["ResolvedSpec"]) -> None: ...


@hookspec
def canary_select_report(specs: list["TestSpec"]) -> None:
    raise NotImplementedError
