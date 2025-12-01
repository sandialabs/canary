# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import atexit
from pathlib import Path

import schema

import _canary.config as config
import _canary.enums as enums
from _canary.build import Builder
from _canary.collect import Collector
from _canary.config.argparsing import Parser
from _canary.config.config import Config
from _canary.enums import centered_parameter_space
from _canary.enums import list_parameter_space
from _canary.enums import random_parameter_space
from _canary.error import TestDiffed
from _canary.error import TestFailed
from _canary.error import TestSkipped
from _canary.generator import AbstractTestGenerator
from _canary.hookspec import hookimpl
from _canary.hookspec import hookspec
from _canary.main import console_main
from _canary.pluginmanager import CanaryPluginManager
from _canary.plugins.types import CanaryReporter
from _canary.plugins.types import CanarySubcommand
from _canary.protocols import JobProtocol
from _canary.session import Session
from _canary.testcase import TestCase
from _canary.testexec import ExecutionPolicy
from _canary.testexec import PythonFileExecutionPolicy
from _canary.testexec import SubprocessExecutionPolicy
from _canary.testinst import TestInstance
from _canary.testinst import TestMultiInstance
from _canary.testspec import DependencyPatterns
from _canary.testspec import ResolvedSpec
from _canary.testspec import TestSpec
from _canary.testspec import UnresolvedSpec
from _canary.third_party import color
from _canary.util import _difflib as difflib
from _canary.util import filesystem
from _canary.util import graph
from _canary.util import logging as _logging
from _canary.util import module
from _canary.util import shell
from _canary.util import string
from _canary.util import time
from _canary.util.executable import Executable
from _canary.version import version  # noqa: I001
from _canary.version import version_info  # noqa: I001
from _canary.workspace import NotAWorkspaceError
from _canary.workspace import Workspace

from . import directives
from . import patterns

get_logger = _logging.get_logger
logging = _logging.get_logger()


__all__ = [
    "schema",
    "builder",
    "collector",
    "config",
    "enums",
    "Parser",
    "Config",
    "centered_parameter_space",
    "list_parameter_space",
    "random_parameter_space",
    "TestDiffed",
    "TestFailed",
    "TestSkipped",
    "AbstractTestGenerator",
    "hookimpl",
    "hookspec",
    "console_main",
    "CanaryPluginManager",
    "CanaryReporter",
    "CanarySubcommand",
    "JobProtocol",
    "Session",
    "TestCase",
    "ExecutionPolicy",
    "PythonFileExecutionPolicy",
    "SubprocessExecutionPolicy",
    "TestInstance",
    "TestMultiInstance",
    "DependencyPatterns",
    "ResolvedSpec",
    "TestSpec",
    "UnresolvedSpec",
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


def get_instance(arg_path: Path | str | None = None) -> TestInstance | None:
    from _canary.testinst import load_instance

    try:
        instance = load_instance(arg_path)
    except FileNotFoundError:
        return None
    return instance


def get_testcase(arg_path: Path | str | None = None) -> TestCase | None:
    from _canary.testcase import load_testcase_from_file

    try:
        case = load_testcase_from_file(arg_path)
        atexit.register(lambda: case.save())
    except FileNotFoundError:
        return None
    return case


def __getattr__(name):
    import _canary

    if name == "FILE_SCANNING":
        return _canary.FILE_SCANNING
    elif name == "test":
        test = type("Test", (), {"instance": get_instance()})()
        return test
    raise AttributeError(name)
