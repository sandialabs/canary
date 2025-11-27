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

    from ..collect import Collector
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
@hookspec(firstresult=True)
def canary_collect(collector: "Collector") -> list["AbstractTestGenerator"]:
    raise NotImplementedError


@hookspec
def canary_collectstart(collector: "Collector") -> None:
    """Start collection.

    Args:
      collector: To add file patterns to the collector call
      :py:func:`collector.add_file_patterns(...) <Collector.add_file_patterns>`.  To add directory
      names to skip call :py:func:`collector.add_skip_dirs(...) <Collector.add_skip_dirs>`.

    """


@hookspec(firstresult=True)
def canary_collectitems(collector: "Collector") -> None:
    raise NotImplementedError


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


@hookspec(firstresult=True)
def canary_generate(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["ResolvedSpec"]:
    """Perform the generation phase

    The default generation phase is this:

    1. Starting from ``session`` as the initial collector:

      1. ``pytest_collectstart(collector)``
      2. ``report = pytest_make_collect_report(collector)``
      3. ``pytest_exception_interact(collector, call, report)`` if an interactive exception occurred
      4. For each collected node:

        1. If an item, ``pytest_itemcollected(item)``
        2. If a collector, recurse into it.

      5. ``pytest_collectreport(report)``

    2. ``pytest_collection_modifyitems(session, config, items)``

      1. ``pytest_deselected(items)`` for any deselected items (may be called multiple times)

    3. ``pytest_collection_finish(session)``
    4. Set ``session.items`` to the list of collected items
    5. Set ``session.testscollected`` to the number of collected items

    You can implement this hook to only perform some action before collection,
    for example the terminal plugin uses it to start displaying the collection
    counter (and returns `None`).

    :param pytest.Session session: The pytest session object.
    """

    raise NotImplementedError


@hookspec
def canary_generate_modifyitems(specs: list["ResolvedSpec"]) -> None: ...


@hookspec
def canary_generate_report(specs: list["ResolvedSpec"]) -> None: ...


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
