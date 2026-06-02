# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import atexit
from pathlib import Path

import schema

import _canary.config as config
import _canary.enums as enums
import _canary.status as status
from _canary import version as _v
from _canary.collect import Collector
from _canary.config.argparsing import Parser
from _canary.config.config import Config
from _canary.enums import centered_parameter_space
from _canary.enums import list_parameter_space
from _canary.enums import random_parameter_space
from _canary.error import TestDiffed
from _canary.error import TestFailed
from _canary.error import TestSkipped
from _canary.generate import Generator
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
from _canary.main import console_main
from _canary.pluginmanager import CanaryPluginManager
from _canary.plugins.types import CanaryReporter
from _canary.plugins.types import CanarySubcommand
from _canary.rules import Rule
from _canary.rules import RuleOutcome
from _canary.rules import RuntimeRule
from _canary.select import RuntimeSelector
from _canary.select import Selector
from _canary.testcase import TestCase
from _canary.testinst import LockFileNotFoundError
from _canary.testinst import MissingTestInstance
from _canary.testinst import TestInstance
from _canary.testinst import TestMultiInstance
from _canary.util import _difflib as difflib
from _canary.util import filesystem
from _canary.util import graph
from _canary.util import logging
from _canary.util import module
from _canary.util import rich as color
from _canary.util import shell
from _canary.util import string
from _canary.util import time
from _canary.util.executable import Executable
from _canary.workspace import NotAWorkspaceError
from _canary.workspace import Session
from _canary.workspace import ViewSettings
from _canary.workspace import Workspace

from . import directives
from . import patterns

get_logger = logging.get_logger

version = _v.version
version_info = _v.version_info
ResolvedSpec = JobSpec
AbstractTestGenerator = AbstractSpecGenerator
del _v


__all__ = [
    "schema",
    "Generator",
    "Collector",
    "config",
    "status",
    "enums",
    "Parser",
    "Config",
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


def __getattr__(name):
    import _canary

    if name == "FILE_SCANNING":
        return _canary.FILE_SCANNING
    elif name == "test":
        test = type("Test", (), {"instance": get_instance()})()
        return test
    raise AttributeError(name)
