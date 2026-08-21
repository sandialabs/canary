# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import Any

from schema import Optional
from schema import Schema

import canary
from _canary.util import cpu_count

from .ctest import CTestTestGenerator
from .ctest import finish_ctest
from .ctest import read_resource_specs
from .ctest import setup_ctest

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_collectstart(collector: canary.Collector) -> None:
    collector.add_generator(CTestTestGenerator)


@canary.hookimpl
def canary_collect_modifyitems(collector: canary.Collector) -> None:
    ctest_files: dict[str, list[str]] = {}
    for root, path in collector.iter_files():
        if os.path.basename(path) == "CTestTestfile.cmake":
            ctest_files.setdefault(root, []).append(path)
    for root, paths in ctest_files.items():
        if len(paths) > 1:
            paths.sort(key=lambda p: (p.split(os.sep), p))
            for path in paths[1:]:
                collector.remove_file(root, path)


@canary.hookimpl
def canary_runteststart(case: canary.Job) -> None:
    if case.spec.file.suffix == ".cmake":
        setup_ctest(case)


@canary.hookimpl
def canary_runtest_finish(case: canary.Job) -> None:
    if case.spec.file.suffix == ".cmake":
        finish_ctest(case)


@canary.hookimpl
def canary_addconfig(config: canary.Config):
    config.add_section(name="cmake", schema=cmake_schema)


@canary.hookimpl
def canary_configure(config: canary.Config):
    config.set("run:timeout:ctest", 1500.0)


@canary.hookimpl(specname="canary_addoption")
def add_ctest_options(parser: canary.Parser) -> None:
    parser.add_argument(
        "--ctest-config",
        metavar="cfg",
        dest="canary_cmake_ctest_config",
        group="ctest options",
        command=["run", "find"],
        help="Choose configuration to test",
    )
    parser.add_argument(
        "--ctest-test-timeout",
        metavar="T",
        dest="canary_cmake_test_timeout",
        type=canary.time.time_in_seconds,
        group="ctest options",
        command="run",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ctest-resource-spec-file",
        metavar="FILE",
        dest="canary_cmake_resource_spec_file",
        group="ctest options",
        command="run",
        help="Set the resource spec file to use.",
    )
    parser.add_argument(
        "--recurse-ctest",
        group="ctest options",
        dest="canary_cmake_recurse_ctest",
        action="store_true",
        default=False,
        command=["run", "find"],
        help="Recurse CMake binary directory for test files.  CTest tests can be detected "
        "from the root CTestTestfile.cmake, so this is option is not necessary unless there "
        "is a mix of CTests and other test types in the binary directory",
    )
    parser.add_argument(
        "--output-on-failure",
        nargs=0,
        action=MapToShowCapture,
        group="ctest options",
        command="run",
        help="Alias for --show-capture",
    )


class MapToShowCapture(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        args.show_capture = "oe"
        setattr(args, self.dest, True)


@canary.hookimpl(tryfirst=True)
def canary_resource_pool_fill(config: canary.Config) -> dict[str, Any] | None:
    f = config.getoption("canary_cmake_resource_spec_file")
    if not f:
        return None

    logger.info("Setting resource pool from ctest resource spec file")

    resource_specs = read_resource_specs(f)
    ctest_resources = dict(resource_specs["local"])

    # CTest resource specs often describe accelerator/custom resources but may
    # omit CPUs. Since this hook creates the base pool, provide the same default
    # CPU discovery used by Canary's local resource-pool creator.
    if "cpus" not in ctest_resources:
        ht: bool = config.getoption("resource_pool_enable_hyperthreads", False)
        cpus = int(var) if (var := os.getenv("CANARY_TESTING_CPUS")) else cpu_count(logical=ht)
        ctest_resources["cpus"] = [{"id": str(j), "slots": 1} for j in range(cpus)]
    return {
        "allow_multinode": True,
        "additional_properties": {"ctest": {"resource_spec_file": os.path.abspath(f)}},
        "nodes": [{"id": os.uname().nodename, "resources": ctest_resources}],
    }


cmake_schema = Schema(
    {
        Optional("project"): Optional(str),
        Optional("type"): Optional(str),
        Optional("date"): Optional(str),
        Optional("build_directory"): Optional(str),
        Optional("source_directory"): Optional(str),
        Optional("compiler"): {
            Optional("vendor"): Optional(str),
            Optional("version"): Optional(str),
            Optional("paths"): {
                Optional("cc"): Optional(str),
                Optional("cxx"): Optional(str),
                Optional("fc"): Optional(str),
                Optional("mpicc"): Optional(str),
                Optional("mpicxx"): Optional(str),
                Optional("mpifc"): Optional(str),
            },
            Optional("cc"): Optional(str),
            Optional("cxx"): Optional(str),
            Optional("fc"): Optional(str),
            Optional("mpicc"): Optional(str),
            Optional("mpicxx"): Optional(str),
            Optional("mpifc"): Optional(str),
        },
    },
    ignore_extra_keys=True,
)
