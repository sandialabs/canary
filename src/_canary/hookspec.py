# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# mypy: disable-error-code=empty-body

from typing import TYPE_CHECKING
from typing import Any
from typing import Type

import pluggy

from .plugins.types import CanarySubcommand

if TYPE_CHECKING:
    from multiprocessing import Queue

    from .collect import Collector
    from .config.argparsing import Parser
    from .config.config import Config as CanaryConfig
    from .generate import Generator
    from .generator import AbstractTestGenerator
    from .launcher import Launcher
    from .pluginmanager import CanaryPluginManager
    from .resource_pool.rpool import Outcome
    from .runtest import Runner
    from .select import RuntimeSelector
    from .select import Selector
    from .testcase import TestCase
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


@hookspec
def canary_sessionstart(session: "Session") -> None: ...


@hookspec
def canary_sessionfinish(session: "Session") -> None: ...


# -------------------------------------------------------------------------
# collection hooks
# -------------------------------------------------------------------------
@hookspec
def canary_collectstart(collector: "Collector") -> None:
    """Start collection.

    Args:
      collector: To add generators to the collector call
      :py:func:`collector.add_generator(...) <Collector.add_generator>`.  To add directory
      names to skip call :py:func:`collector.add_skip_dirs(...) <Collector.add_skip_dirs>`.

    """


@hookspec
def canary_collect_modifyitems(collector: "Collector") -> None:
    """Called after collection of test files is complete.  May filter or re-order items in place"""
    raise NotImplementedError


@hookspec
def canary_collect_report(collector: "Collector") -> None:
    """Write a report to the console for collected items"""
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
def canary_generatestart(generator: "Generator") -> None:
    """Starts the generate process.

    Args:
        generator: The generator to start.
    """


@hookspec
def canary_generate_modifyitems(generator: "Generator") -> None:
    """Modifies the generate items.

    Args:
        generator: The generator to modify.
    """


@hookspec
def canary_generate_report(generator: "Generator") -> None:
    """Reports the generation results.

    Args:
        generator: The generator to report on.
    """


# -------------------------------------------------------------------------
# selection hooks
# -------------------------------------------------------------------------
@hookspec
def canary_selectstart(selector: "Selector") -> None:
    """Starts the selection process.

    Args:
        selector: The selector to start.
    """


@hookspec
def canary_select_modifyitems(selector: "Selector") -> None:
    """Modifies the selection items.

    Args:
        selector: The selector to modify.
    """


@hookspec
def canary_select_report(selector: "Selector") -> None:
    """Reports the selection results.

    Args:
        selector: The selector to report on.
    """


# -------------------------------------------------------------------------
# runtime selection hooks
# -------------------------------------------------------------------------
@hookspec
def canary_rtselectstart(selector: "RuntimeSelector") -> None:
    """Starts the selection process.

    Args:
        selector: The selector to start.
    """


@hookspec
def canary_rtselect_modifyitems(selector: "RuntimeSelector") -> None:
    """Modifies the selection items.

    Args:
        selector: The selector to modify.
    """


@hookspec
def canary_rtselect_report(selector: "RuntimeSelector") -> None:
    """Reports the selection results.

    Args:
        selector: The selector to report on.
    """


# -------------------------------------------------------------------------
# runtest hooks
# -------------------------------------------------------------------------
@hookspec
def canary_runtests_start(runner: "Runner") -> bool:
    """Called at the beginning of `canary run`"""
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtests(runner: "Runner") -> None:
    """Runs the tests.

    Args:
        runner: The runner to run.

    """


@hookspec
def canary_runtests_report(runner: "Runner") -> None:
    """Reports the test results.

    Args:
        runner: The runner to report on.
    """


@hookspec(firstresult=True)
def canary_runtest_launcher(case: "TestCase") -> "Launcher":
    """Returns the launcher for a test case.

    Args:
        case: The test case.

    Returns:
        The launcher.

    Note:

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runteststart(case: "TestCase") -> bool:
    """Called to perform the setup phase for a test case.

    The default implementation runs ``case.setup()``.

    Args:
        The test case.

    Note:
      This function is called inside the test case's working directory

    """
    raise NotImplementedError


@hookspec(firstresult=True)
def canary_runtest(case: "TestCase", queue: "Queue") -> bool:
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


# -------------------------------------------------------------------------
# resource pool hooks
# -------------------------------------------------------------------------


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
