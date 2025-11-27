# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import Any
from typing import Generator

from schema import And
from schema import Optional
from schema import Or
from schema import Schema
from schema import Use

import canary

from .cdash import CDashReporter
from .ctest import CTestTestGenerator
from .ctest import finish_ctest
from .ctest import read_resource_specs
from .ctest import setup_ctest

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_collectstart(collector) -> None:
    collector.add_file_patterns("CTestTestfile.cmake")


@canary.hookimpl
def canary_collect_modifyitems(collector) -> None:
    ctest_files: dict[str, list[str]] = {}
    for root, path in collector.iter_files():
        if os.path.basename(path) == "CTestTestfile.cmake":
            ctest_files.setdefault(root, []).append(path)
    for root, paths in ctest_files.items():
        if len(paths) > 1:
            paths.sort(key=lambda p: (p.split(os.sep), p))
            for path in paths[1:]:
                collector.remove_file(root, path)


@canary.hookimpl(specname="canary_testcase_generator")
def ctest_test_generator(root: str, path: str | None) -> canary.AbstractTestGenerator | None:
    if CTestTestGenerator.matches(root if path is None else os.path.join(root, path)):
        return CTestTestGenerator(root, path=path)
    return None


@canary.hookimpl
def canary_testcase_execution_policy(case: canary.TestCase) -> canary.ExecutionPolicy | None:
    if case.spec.file.suffix == ".cmake":
        return canary.SubprocessExecutionPolicy(["./runtest.sh"])
    return None


@canary.hookimpl
def canary_testcase_modify(case: canary.TestCase) -> None:
    if case.spec.file.suffix == ".cmake":
        # concatenate stdout and stderr
        case.stderr = None


@canary.hookimpl
def canary_testcase_setup(case: canary.TestCase) -> None:
    if case.spec.file.suffix == ".cmake":
        setup_ctest(case)


@canary.hookimpl
def canary_testcase_finish(case: canary.TestCase) -> None:
    if case.spec.file.suffix == ".cmake":
        finish_ctest(case)


@canary.hookimpl(specname="canary_configure")
def add_default_ctest_timeout(config: canary.Config):
    config.set("timeout:ctest", 1500.0)


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


class CDashHooks:
    @canary.hookspec
    def canary_cdash_labels_for_subproject(self) -> list[str] | None:
        """Return a list of subproject labels to be added to Test.xml reports"""
        ...

    @canary.hookspec(firstresult=True)
    def canary_cdash_subproject_label(self, case: "canary.TestCase") -> str | None:
        """Return a subproject label for ``case`` that will be added in Test.xml reports"""
        ...

    @canary.hookspec(firstresult=True)
    def canary_cdash_labels(self, case: "canary.TestCase") -> list[str] | None:
        """Return CDash labels for ``case``"""
        ...

    @canary.hookspec
    def canary_cdash_artifacts(self, case: "canary.TestCase") -> list[dict[str, str]] | None:
        """Return artifacts to transmit to CDash"""
        ...


@canary.hookimpl
def canary_session_reporter() -> canary.CanaryReporter:
    return CDashReporter()


@canary.hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager"):
    pluginmanager.add_hookspecs(CDashHooks)


@canary.hookimpl(trylast=True)
def canary_cdash_labels(case: canary.TestCase) -> list[str]:
    """Default implementation: return the test case's keywords"""
    return list(case.spec.keywords)


@canary.hookimpl
def canary_resource_pool_fill(config: canary.Config, pool: dict[str, dict[str, Any]]) -> None:
    if f := config.getoption("canary_cmake_resource_spec_file"):
        logger.info("Setting resource pool from ctest resource spec file")
        pool["additional_properties"].clear()
        pool["additional_properties"]["ctest"] = {"resource_spec_file": os.path.abspath(f)}
        resource_specs = read_resource_specs(f)
        cpu_spec = pool["resources"].pop("cpus")
        pool["resources"].clear()
        pool["resources"].update(resource_specs["local"])
        if "cpus" not in pool["resources"]:
            pool["resources"]["cpus"] = cpu_spec


@canary.hookimpl(wrapper=True)
def canary_cdash_artifacts(case: canary.TestCase) -> Generator[None, None, list[dict[str, str]]]:
    """Default implementation: return the test case's keywords"""
    schema = Schema(
        {
            "file": And(Or(str, Path), Use(str)),
            Optional("when", default="always"): Or("never", "always", "on_success", "on_failure"),
        }
    )
    artifacts = list(case.spec.artifacts) or []
    result = yield
    artifacts.extend([_ for _ in result if _])
    for i, artifact in enumerate(artifacts):
        artifacts[i] = schema.validate(artifact)
    return artifacts
