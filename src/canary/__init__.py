# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# ---------------------------------------------------------------------------
# Eager imports — needed at test-script runtime
# ---------------------------------------------------------------------------
# These are imported unconditionally because test scripts (*.pyt, *.vvt) need
# them at execution time without any attribute access indirection.

import argparse
import atexit
from pathlib import Path

import schema

import _canary.config as config
import _canary.enums as enums
import _canary.status as status
from _canary.config.argparsing import Parser
from _canary.config.config import Config
from _canary.enums import centered_parameter_space
from _canary.enums import list_parameter_space
from _canary.enums import random_parameter_space
from _canary.error import TestDiffed
from _canary.error import TestFailed
from _canary.error import TestSkipped
from _canary.generator import AbstractSpecGenerator
from _canary.hookspec import hookimpl
from _canary.hookspec import hookspec
from _canary.ir import DependencySelector
from _canary.ir import JobSpecIR
from _canary.job import BaseJob
from _canary.job import Job
from _canary.jobspec import Artifact
from _canary.jobspec import Asset
from _canary.jobspec import JobSpec
from _canary.jobspec import Mask
from _canary.launcher import Launcher
from _canary.launcher import SubprocessLauncher
from _canary.rules import Rule
from _canary.rules import RuleOutcome
from _canary.rules import RuntimeRule
from _canary.testcase import TestCase
from _canary.testinst import LockFileNotFoundError
from _canary.testinst import MissingTestInstance
from _canary.testinst import TestInstance
from _canary.testinst import TestMultiInstance
from _canary.util import _difflib as difflib
from _canary.util import filesystem
from _canary.util import logging
from _canary.util import module
from _canary.util import rich as color
from _canary.util import shell
from _canary.util import string
from _canary.util import time
from _canary.util.executable import Executable

from . import directives
from . import patterns

get_logger = logging.get_logger

ResolvedSpec = JobSpec
AbstractTestGenerator = AbstractSpecGenerator


# ---------------------------------------------------------------------------
# Public API declarations
# ---------------------------------------------------------------------------
# CLI-only names (CanarySubcommand, CanaryReporter, Collector, console_main,
# Runner, NotAWorkspaceError, Session, ViewSettings, Workspace) are resolved
# lazily via __getattr__ below to avoid loading ~55 ms of CLI-only modules
# in every test subprocess that does `import canary`.

__all__ = [
    "schema",
    "Generator",
    "Collector",
    "config",
    "status",
    "enums",
    "Parser",
    "Config",
    "Runner",
    "Selector",
    "Rule",
    "RuntimeSelector",
    "RuntimeRule",
    "RuleOutcome",
    "Mask",
    "centered_parameter_space",
    "list_parameter_space",
    "random_parameter_space",
    "TestDiffed",
    "TestFailed",
    "TestSkipped",
    "AbstractSpecGenerator",
    "AbstractTestGenerator",
    "hookimpl",
    "hookspec",
    "console_main",
    "CanaryPluginManager",
    "CanaryReporter",
    "CanarySubcommand",
    "BaseJob",
    "Job",
    "TestCase",
    "Launcher",
    "logging",
    "MissingTestInstance",
    "SubprocessLauncher",
    "TestInstance",
    "TestMultiInstance",
    "DependencySelector",
    "Artifact",
    "Asset",
    "JobSpec",
    "ResolvedSpec",
    "JobSpecIR",
    "color",
    "difflib",
    "filesystem",
    "graph",
    "module",
    "shell",
    "string",
    "time",
    "Executable",
    "version",
    "version_info",
    "NotAWorkspaceError",
    "Session",
    "ViewSettings",
    "Workspace",
    "directives",
    "patterns",
]


class TestParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        namespace, unknown_args = super().parse_known_args(args, namespace)
        namespace.extra_args = unknown_args
        return namespace


def make_argument_parser() -> TestParser:
    parser = TestParser()
    parser.add_argument("--stage", default="run")
    parser.add_argument("--baseline", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", action="store_true")
    group.add_argument("--analyze", action="store_true")
    group.add_argument("--execute-analysis-sections", action="store_true")
    return parser


make_std_parser = make_argument_parser


def get_instance(arg_path: Path | str | None = None) -> TestInstance | MissingTestInstance:
    from _canary.testinst import load_instance

    try:
        return load_instance(arg_path)
    except LockFileNotFoundError:
        return MissingTestInstance(arg_path)


def get_job(arg_path: Path | str | None = None) -> Job | None:
    from _canary.job import load_job_from_file

    try:
        job = load_job_from_file(arg_path)
        atexit.register(lambda: job.save())
    except FileNotFoundError:
        return None
    return job


get_testcase = get_job


# ---------------------------------------------------------------------------
# Lazy attribute loader
# ---------------------------------------------------------------------------
# Names listed here are loaded on first access only.  This keeps `import canary`
# fast for test subprocesses while remaining fully transparent to CLI code and
# extension authors.

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # name -> (module_path, attribute_in_module)
    "CanarySubcommand": ("_canary.subcommands.base", "CanarySubcommand"),
    "CanaryReporter": ("_canary.reporters.reporter", "CanaryReporter"),
    "CanaryPluginManager": ("_canary.pluginmanager", "CanaryPluginManager"),
    "Collector": ("_canary.collect", "Collector"),
    "console_main": ("_canary.main", "console_main"),
    "Generator": ("_canary.generate", "Generator"),
    "RuntimeSelector": ("_canary.select", "RuntimeSelector"),
    "Selector": ("_canary.select", "Selector"),
    "Runner": ("_canary.runtest", "Runner"),
    "NotAWorkspaceError": ("_canary.workspace", "NotAWorkspaceError"),
    "Session": ("_canary.workspace", "Session"),
    "Workspace": ("_canary.workspace", "Workspace"),
    "ViewSettings": ("_canary.view", "ViewSettings"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        mod_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(mod_path)
        value = getattr(mod, attr)
        # Cache in module globals so subsequent accesses skip __getattr__
        globals()[name] = value
        return value

    if name in ("version", "__version__", "version_info", "__version_info__"):
        from _canary import version as _v

        return getattr(_v, name)

    import canary_pyt

    if name == "FILE_SCANNING":
        return canary_pyt.FILE_SCANNING
    elif name == "test":
        test = type("Test", (), {"instance": get_instance()})()
        return test
    raise AttributeError(name)
