# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# mypy: disable-error-code=empty-body

from typing import TYPE_CHECKING
from typing import Any
from typing import Type

import pluggy

from .plugins.types import CanaryReporter
from .plugins.types import CanarySubcommand

if TYPE_CHECKING:
    from multiprocessing import Queue

    from .build import Builder
    from .collect import Collector
    from .config.argparsing import Parser
    from .config.config import Config as CanaryConfig
    from .generator import AbstractTestGenerator
    from .pluginmanager import CanaryPluginManager
    from .resource_pool.rpool import Outcome
    from .select import Selector
    from .testcase import TestCase
    from .testexec import ExecutionPolicy
    from .workspace import Session


project_name = "canary"
hookspec = pluggy.HookspecMarker(project_name)
hookimpl = pluggy.HookimplMarker(project_name)


# -------------------------------------------------------------------------
# Initialization hooks
# -------------------------------------------------------------------------


@hookspec
def canary_addhooks(pluginmanager: "CanaryPluginManager") -> None:
    """Called at plugin registration time to allow adding new hooks via a call to
    ``pluginmanager.add_hookspecs(module_or_class, prefix)``.

    Args:
      pluginmanager: The canary plugin manager.

    .. note::
        This hook is incompatible with ``hookwrapper=True``.

    """


@hookspec
def canary_addoption(parser: "Parser") -> None:
    """Register argparse options, called once at the beginning of a test run.

    Args:
      parser: To add command line options, call
        :py:func:`parser.add_argument(...) <config.argparsing.Parser.add_argument>`.

    Options can later be accessed through the :py:class:`config <canary.Config>` object:

    - :py:func:`config.getoption(name) <canary.Config.getoption>` to
      retrieve the value of a command line option.

    .. note::
        This hook is incompatible with ``hookwrapper=True``.

    """


@hookspec
def canary_addcommand(parser: "Parser") -> None:
    """Add a subcommand to Canary

    Args:
      parser: To add a command, call
        :py:func:`parser.add_command(...) <config.argparsing.Parser.add_command>`.

    .. note::
        The command should be a subclass of :py:class:`canary.CanarySubcommand`

    Example:

    .. code-block:: python

       import argparse
       import canary

       class MyCommand(canary.CanarySubcommand):
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
    """DEPRECATED: use canary_addcommand"""
    raise NotImplementedError


@hookspec
def canary_configure(config: "CanaryConfig") -> None:
    """Allow plugins to perform initial configuration.

    This hook is called for every plugin and after command line options have been parsed.

    .. note::
        This hook is incompatible with ``hookwrapper=True``.

    Args:
      config: The canary config object.

    """


# -------------------------------------------------------------------------
# collection hooks
# -------------------------------------------------------------------------
@hookspec
def canary_collectstart(collector: "Collector") -> None:
    """Start collection.

    Args:
      collector: To add file patterns to the collector call
      :py:func:`collector.add_file_patterns(...) <Collector.add_file_patterns>`.  To add directory
      names to skip call :py:func:`collector.add_skip_dirs(...) <Collector.add_skip_dirs>`.

    """


@hookspec
def canary_collect_modifyitems(collector: "Collector") -> None:
    """Filter tests we don't want to generate"""
    raise NotImplementedError


@hookspec
def canary_collect_report(collector: "Collector") -> None:
    """Filter tests we don't want to generate"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_testcase_generator(
    root: str, path: str | None
) -> "AbstractTestGenerator | Type[AbstractTestGenerator]":
    """Returns an implementation of AbstractTestGenerator"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_generator(root: str, path: str | None) -> "AbstractTestGenerator":
    """DEPRECATED: Use canary_testcase_generator"""
    raise NotImplementedError


# -------------------------------------------------------------------------
# generation hooks
# -------------------------------------------------------------------------


@hookspec
def canary_buildstart(builder: "Builder") -> None: ...


@hookspec
def canary_build_modifyitems(builder: "Builder") -> None: ...


@hookspec
def canary_build_report(builder: "Builder") -> None: ...


# -------------------------------------------------------------------------
# selection hooks
# -------------------------------------------------------------------------


@hookspec
def canary_selectstart(selector: "Selector") -> None: ...


@hookspec
def canary_select_modifyitems(selector: "Selector") -> None: ...


@hookspec
def canary_select_report(selector: "Selector") -> None: ...


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
def canary_runtests_start() -> None:
    """Called at the beginning of `canary run`"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtests(cases: list["TestCase"]) -> int:
    raise NotImplementedError


@hookspec
def canary_runtests_report(cases: list["TestCase"], include_pass: bool, truncate: int) -> None:
    raise NotImplementedError


@hookspec
def canary_session_reporter() -> CanaryReporter:
    """Register Canary report type"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtest_execution_policy(case: "TestCase") -> "ExecutionPolicy":
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtest_setup(case: "TestCase") -> bool:
    """Called to perform the setup phase for a test case.

    The default implementation runs ``case.setup()``.

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtest_exec(case: "TestCase", queue: "Queue") -> bool:
    """Called to run the test case

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtest_finish(case: "TestCase") -> bool:
    """Called to perform the finishing tasks for the test case

    The default implementation runs ``case.finish()``

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec
def canary_resource_pool_fill(config: "CanaryConfig", pool: dict[str, dict[str, Any]]) -> None:
    """Fill ``resources`` with available resources."""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_resource_pool_accommodates(case: "TestCase") -> "Outcome":
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
