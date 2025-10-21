import argparse
import os
from typing import Any

import canary

from .cdash import CDashReporter
from .ctest import CTestTestGenerator
from .ctest import read_resource_specs

logger = canary.get_logger(__name__)


@canary.hookimpl(specname="canary_testcase_generator")
def ctest_test_generator(root: str, path: str | None) -> canary.AbstractTestGenerator | None:
    if CTestTestGenerator.matches(root if path is None else os.path.join(root, path)):
        return CTestTestGenerator(root, path=path)
    return None


@canary.hookimpl(specname="canary_configure")
def add_default_ctest_timeout(config: canary.Config):
    config.set("config:timeout:ctest", 1500.0, scope="defaults")


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


@canary.hookimpl
def canary_session_reporter() -> canary.CanaryReporter:
    return CDashReporter()


@canary.hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager"):
    pluginmanager.add_hookspecs(CDashHooks)


@canary.hookimpl(trylast=True)
def canary_cdash_labels(case: canary.TestCase) -> list[str]:
    """Default implementation: return the test case's keywords"""
    return list(case.keywords)


@canary.hookimpl
def canary_resource_pool_fill(
    config: canary.Config, resources: dict[str, list[dict[str, Any]]]
) -> None:
    if f := config.getoption("canary_cmake_resource_spec_file"):
        logger.info("Setting resource pool from ctest resource spec file")
        resource_specs = read_resource_specs(f)
        for rtype, rspec in resource_specs["local"].items():
            resources[rtype] = rspec
