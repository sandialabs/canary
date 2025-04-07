# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import copy
import io
import json
import os
import re
import shlex
import subprocess
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Type

from ... import config
from ...generator import AbstractTestGenerator
from ...test.case import DependencyPatterns
from ...test.case import TestCase
from ...util import graph
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import is_exe
from ...util.filesystem import set_executable
from ...util.filesystem import which
from ...util.filesystem import working_dir
from ...util.time import time_in_seconds
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.config import Config

warning_cache = set()


def warn_unsupported_ctest_option(option: str) -> None:
    if option in warning_cache:
        return
    file = io.StringIO()
    file.write(f"The ctest test property {option.upper()!r} is currently not supported, ")
    file.write("contact the canary developers to implement this property")
    logging.warning(file.getvalue())
    warning_cache.add(option)


class CTestTestGenerator(AbstractTestGenerator):
    def __init__(self, root: str, path: str | None = None) -> None:
        # CTest works with resolved paths
        super().__init__(os.path.abspath(root), path=path)
        self.owners: list[str] = []

    @classmethod
    def matches(cls, path: str) -> bool:
        matches = cls.always_matches(path)
        if matches:
            return True
        return False

    def stop_recursion(self) -> bool:
        if config.getoption("recurse_ctest", False):
            return False
        return True

    @classmethod
    def always_matches(cls, path: str) -> bool:
        return os.path.basename(path) == "CTestTestfile.cmake"

    def lock(self, on_options: list[str] | None = None) -> list[TestCase]:
        cmake = find_cmake()
        if cmake is None:
            logging.warning("cmake not found, test cases cannot be generated")
            return []
        tests = self.load()
        if not tests:
            return []
        cases: list[CTestTestCase] = []
        realpath = os.path.realpath
        for family, details in tests.items():
            path = os.path.relpath(details["ctestfile"], self.root)
            if not os.path.exists(os.path.join(self.root, path)):
                path = os.path.relpath(realpath(details["ctestfile"]), realpath(self.root))
            case = CTestTestCase(file_root=self.root, file_path=path, family=family, **details)
            cases.append(case)
        self.resolve_inter_dependencies(cases)
        self.resolve_fixtures(cases)
        return cases  # type: ignore

    def describe(self, on_options: list[str] | None = None) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        cases = self.lock(on_options=on_options)
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def load(self) -> dict:
        """Load and transform the tests loaded from CMake into a form understood by nvtest

        ``tests`` is of the form

        ``{NAME: {'command': [...], 'properties': [{'name': ..., 'value': ...}, ...]}, ...}``

        and is transformed in place to the form:

        ``{NAME: {'command': [...], 'prop_name': prop_value, ...}, ...}``

        """
        tests = load(self.file)
        if not tests:
            return {}
        for name, defn in tests.items():
            transformed: dict[str, Any] = {"command": defn["command"]}
            transformed["ctestfile"] = defn["ctestfile"] or self.file
            for prop in defn["properties"]:
                prop_name, prop_value = prop["name"], prop["value"]
                if prop_name == "ENVIRONMENT":
                    prop_value = parse_environment(prop_value)
                elif prop_name == "ENVIRONMENT_MODIFICATION":
                    prop_value = parse_environment_modification(prop_value)
                elif prop_name == "RESOURCE_GROUPS":
                    prop_value = parse_resource_groups(prop_value)
                transformed[prop_name.lower()] = prop_value
            tests[name] = transformed
        return tests

    def resolve_fixtures(self, cases: list["CTestTestCase"]) -> None:
        setup_fixtures: dict[str, list[CTestTestCase]] = {}
        cleanup_fixtures: dict[str, list[CTestTestCase]] = {}
        for case in cases:
            for fixture_name in case.fixtures["setup"]:
                setup_fixtures.setdefault(fixture_name, []).append(case)
            for fixture_name in case.fixtures["cleanup"]:
                cleanup_fixtures.setdefault(fixture_name, []).append(case)
        for case in cases:
            for fixture_name in case.fixtures["required"]:
                if fixture_name in setup_fixtures:
                    for fixture in setup_fixtures[fixture_name]:
                        case.add_dependency(fixture)
                if fixture_name in cleanup_fixtures:
                    for fixture in cleanup_fixtures[fixture_name]:
                        fixture.add_dependency(case)

    def resolve_inter_dependencies(self, cases: list["CTestTestCase"]) -> None:
        logging.debug(f"Resolving dependencies in {self}")
        for case in cases:
            while True:
                if not case.unresolved_dependencies:
                    break
                dep = case.unresolved_dependencies.pop(0)
                matches = dep.evaluate([c for c in cases if c != case])
                for match in matches:
                    case.add_dependency(match)


class CTestTestCase(TestCase):
    def __init__(
        self,
        *,
        file_root: str | None = None,
        file_path: str | None = None,
        family: str | None = None,
        command: list[str] | None = None,
        attached_files: list[str] | None = None,
        attached_files_on_fail: list[str] | None = None,
        cost: float | None = None,
        depends: list[str] | None = None,
        disabled: bool = False,
        environment: dict[str, str] | None = None,
        environment_modification: list[dict[str, str]] | None = None,
        fail_regular_expression: list[str] | None = None,
        fixtures_cleanup: list[str] | None = None,
        fixtures_required: list[str] | None = None,
        fixtures_setup: list[str] | None = None,
        generated_resource_spec_file: str | None = None,
        labels: list[str] | None = None,
        measurement: dict[str, float | str] | None = None,
        pass_regular_expression: list[str] | None = None,
        processor_affinity: bool = False,
        processors: int | None = None,
        required_files: list[str] | None = None,
        resource_groups: list[list[dict[str, Any]]] | None = None,
        resource_lock: list[str] | None = None,
        run_serial: bool = False,
        skip_regular_expression: list[str] | None = None,
        skip_return_code: int | None = None,
        timeout: float | None = None,
        timeout_after_match: dict[str, str | float] | None = None,
        timeout_signal_grace_period: float | None = None,
        timeout_signal_name: str | None = None,
        will_fail: bool | None = None,
        working_directory: str | None = None,
        backtrace_triples: list[str] | None = None,
        ctestfile: str | None = None,
        **kwds,
    ) -> None:
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            keywords=labels,
        )

        self._resource_groups: list[list[dict[str, Any]]] | None = None
        self._required_files: list[str] | None = None
        self._will_fail: bool = will_fail or False
        self._ctestfile = ctestfile
        self.ctest_working_directory = working_directory
        self.timeout_property = timeout

        if command is not None:
            with working_dir(self.execution_directory):
                ns = parse_test_args(command)

            self.assets = []
            self.launcher = ns.launcher
            self.preflags = ns.preflags
            self.exe = ns.command
            self.postflags = ns.postflags

        if processors is not None:
            self.parameters["cpus"] = processors
        elif self.preflags:
            self.parameters["cpus"] = parse_np(self.preflags)

        if depends:
            self.unresolved_dependencies.extend(
                [DependencyPatterns(value=d, result="success", expect="+") for d in depends]
            )

        if environment is not None:
            self.add_default_env(**environment)

        if resource_groups is not None:
            self.resource_groups = resource_groups

        if disabled:
            self.mask = f"Explicitly disabled in {self.file}"

        if attached_files is not None:
            self.artifacts.extend([{"file": f, "when": "always"} for f in attached_files])

        if attached_files_on_fail is not None:
            self.artifacts.extend([{"file": f, "when": "failure"} for f in attached_files_on_fail])

        if run_serial is True:
            self.exclusive = True

        if required_files:
            self.required_files = required_files

        if environment_modification is not None:
            self.apply_environment_modifications(environment_modification)

        self.pass_regular_expression = pass_regular_expression
        self.fail_regular_expression = fail_regular_expression
        self.skip_regular_expression = skip_regular_expression
        self.skip_return_code = skip_return_code
        self.fixtures: dict[str, list[str]] = {"cleanup": [], "required": [], "setup": []}
        if fixtures_cleanup:
            self.fixtures["cleanup"].extend(fixtures_cleanup)
        if fixtures_required:
            self.fixtures["required"].extend(fixtures_required)
        if fixtures_setup:
            self.fixtures["setup"].extend(fixtures_setup)

        if cost is not None:
            warn_unsupported_ctest_option("cost")
        if generated_resource_spec_file is not None:
            warn_unsupported_ctest_option("generated_resource_spec_file")
        if measurement is not None:
            warn_unsupported_ctest_option("measurement")
        if processor_affinity:
            warn_unsupported_ctest_option("processor_affinity")
        if resource_lock is not None:
            warn_unsupported_ctest_option("resource_lock")
        if timeout_after_match is not None:
            warn_unsupported_ctest_option("timeout_after_match")
        if timeout_signal_grace_period is not None:
            warn_unsupported_ctest_option("timeout_signal_grace_period")
        if timeout_signal_name is not None:
            warn_unsupported_ctest_option("timeout_signal_name")

    def set_default_timeout(self) -> None:
        """Sets the default timeout which is 1500 for CMake generated files."""
        timeout: float
        if var := config.getoption("ctest_test_timeout"):
            timeout = float(var)
        elif var := os.getenv("CTEST_TEST_TIMEOUT"):
            timeout = time_in_seconds(var)
        elif self.timeout_property is not None:
            timeout = self.timeout_property
        else:
            timeout = getattr(config.test, "timeout_ctest", 1500.0)
        self._timeout = float(timeout)

    @property
    def file(self) -> str:
        return self.ctestfile

    @property
    def ctestfile(self) -> str:
        assert self._ctestfile is not None
        return self._ctestfile

    @ctestfile.setter
    def ctestfile(self, arg: str) -> None:
        self._ctestfile = arg

    def chain(self, start: str | None = None, anchor: str = ".git") -> str:
        return os.path.relpath(self.file, self.file_root)  # type: ignore

    @property
    def execution_directory(self) -> str:
        if self.ctest_working_directory is not None:
            return self.ctest_working_directory
        return self.binary_dir

    @property
    def binary_dir(self) -> str:
        return os.path.dirname(self.ctestfile)

    def required_resources(self) -> list[list[dict[str, Any]]]:
        # The CTest resource group is already configured but CTest does not include CPUs in the
        # resource groups, so we add it on here as a separate resource group.
        required = copy.deepcopy(self.resource_groups)
        has_cpu = any(inst["type"] == "cpus" for group in required for inst in group)
        if not has_cpu:
            cpus = self.parameters.get("cpus", 1)
            cpu_group: list[dict[str, Any]] = [{"type": "cpus", "slots": 1} for _ in range(cpus)]
            required.append(cpu_group)
        return required

    @property
    def implicit_keywords(self) -> list[str]:
        kwds = super().implicit_keywords
        if "unit" not in kwds:
            kwds.append("unit")
        if "ctest" not in kwds:
            kwds.append("ctest")
        return list(kwds)

    def command(self) -> list[str]:
        command: list[str] = []
        if self.launcher:
            command.append(self.launcher)
            command.extend(self.preflags or [])
        command.append(self.exe)
        command.extend(self.postflags or [])
        return command

    def apply_environment_modifications(self, mods: list[dict[str, str]]) -> None:
        for em in mods:
            op, name, value = em["op"], em["name"], em["value"]
            match op:
                case "set" | "unset":
                    self.modify_env(name, value, action=op)
                case "string_append":
                    self.modify_env(name, f"{os.getenv(name, '')}{value}", action="set")
                case "string_prepend":
                    self.modify_env(name, f"{value}{os.getenv(name, '')}", action="set")
                case "path_list_append":
                    self.modify_env(name, value, action="append-path", sep=":")
                case "path_list_prepend":
                    self.modify_env(name, value, action="prepend-path", sep=":")
                case "cmake_list_append":
                    self.modify_env(name, value, action="append-path", sep=";")
                case "cmake_list_prepend":
                    self.modify_env(name, value, action="prepend-path", sep=";")

    @contextmanager
    def rc_environ(self, **env: str) -> Generator[None, None, None]:
        with super().rc_environ(**env):
            self.set_resource_groups_vars()
            yield

    def set_resource_groups_vars(self) -> None:
        # some resources may have been added to the required resources even if they aren't in the
        # resource groups (eg, cpus).  make sure to remove them so they don't unexpectedly appear
        # in the environment variables
        resource_group_count: int = 0
        resource_group_types = {inst["type"] for group in self.resource_groups for inst in group}
        for i, spec in enumerate(self.resources):
            types = sorted(resource_group_types & spec.keys())
            if not types:
                continue
            resource_group_count += 1
            os.environ[f"CTEST_RESOURCE_GROUP_{i}"] = ",".join(types)
            for type, items in spec.items():
                if type not in types:
                    continue
                key = f"CTEST_RESOURCE_GROUP_{i}_{type.upper()}"
                values = []
                for item in items:
                    # use LID since CTest is not designed for multi-node execution
                    _, lid = config.resource_pool.local_ids(type, item["gid"])
                    values.append(f"id:{lid},slots:{item['slots']}")
                os.environ[key] = ";".join(values)
        os.environ["CTEST_RESOURCE_GROUP_COUNT"] = str(resource_group_count)

    def setup(self) -> None:
        super().setup()
        with working_dir(self.working_directory):
            sh = which("sh")
            with open("runtest", "w") as fh:
                fh.write(f"#!{sh}\n")
                fh.write(f"cd {self.execution_directory}\n")
                fh.write(shlex.join(self.command()))
            set_executable("runtest")

    def finish(self, update_stats: bool = True) -> None:
        if update_stats:
            self.cache_last_run()
        self.concatenate_logs()
        file = self.logfile("run")

        if self.status.value in ("timeout", "skipped", "cancelled", "not_run"):
            config.plugin_manager.hook.canary_testcase_finish(case=self, stage="")
            self.save()
            return

        if self.pass_regular_expression is not None:
            for regex in self.pass_regular_expression:
                if file_contains(file, regex):
                    self.status.set("success")
                    break
            else:
                regex = ", ".join(self.pass_regular_expression)
                self.status.set("failed", f"Regular expressions {regex} not found in {file}")

        if self.skip_return_code is not None:
            if self.returncode == self.skip_return_code:
                self.status.set("skipped", f"Return code={self.skip_return_code!r}")

        if self.skip_regular_expression is not None:
            for regex in self.skip_regular_expression:
                if file_contains(file, regex):
                    self.status.set("skipped", f"Regular expression {regex!r} found in {file}")
                    break

        if self.fail_regular_expression is not None:
            for regex in self.fail_regular_expression:
                if file_contains(file, regex):
                    self.status.set("failed", f"Regular expression {regex!r} found in {file}")
                    break

        # invert logic
        if self.will_fail:
            if self.status == "success":
                self.status.set("failed", "Test case marked will_fail but succeeded")
            elif self.status.value not in ("skipped",):
                self.status.set("success")

        config.plugin_manager.hook.canary_testcase_finish(case=self, stage="")
        self.save()

    @property
    def resource_groups(self) -> list[list[dict[str, Any]]]:
        return self._resource_groups or []

    @resource_groups.setter
    def resource_groups(self, arg: list[list[dict[str, Any]]]) -> None:
        self._resource_groups = arg
        gpus: int = 0
        for group in arg:
            for item in group:
                if item["type"] == "gpus":
                    gpus += item["slots"]  # type: ignore
        self.parameters["gpus"] = gpus

    @property
    def required_files(self) -> list[str]:
        return self._required_files or []

    @required_files.setter
    def required_files(self, arg: list[str]) -> None:
        self._required_files = list(arg)
        for file in arg:
            if not os.path.exists(file):
                logging.debug(f"{self}: missing required file: {file}")

    @property
    def will_fail(self) -> bool:
        return self._will_fail

    @will_fail.setter
    def will_fail(self, arg: bool) -> None:
        self._will_fail = bool(arg)


def is_mpi_launcher(arg: str) -> bool:
    launchers = ("mpiexec", "mpirun", "srun", "jsrun")
    return is_exe(arg) and arg.endswith(launchers)


def parse_test_args(args: list[str]) -> argparse.Namespace:
    """Look for command and or mpi runner"""
    ns = argparse.Namespace(launcher=None, preflags=None)
    iter_args = iter(args)
    arg = next(iter_args)
    if is_mpi_launcher(arg):
        ns.launcher = arg
        ns.preflags = []
        for arg in iter_args:
            if is_exe(arg):
                break
            elif is_exe(os.path.abspath(arg)):
                arg = os.path.abspath(arg)
            else:
                ns.preflags.append(arg)
        else:
            s = " ".join(args)
            logging.debug(f"Unable to find test program in {s}")
            ns.launcher = None
            arg = args[0]
            iter_args = iter(args[1:])
    ns.command = arg
    ns.postflags = list(iter_args)
    return ns


def parse_np(args: list[str]) -> int:
    for i, arg in enumerate(args):
        if re.search("^-(n|np|c)$", arg):
            return int(args[i + 1])
        elif re.search("^--np$", arg):
            return int(args[i + 1])
        elif match := re.search("^-(n|np|c)([0-9]+)$", arg):
            return int(match.group(2))
        elif match := re.search("^--np=([0-9]+)$", arg):
            return int(match.group(1))
    return 1


def load(file: str) -> dict[str, Any]:
    """Use ctest --show-only"""
    tests: dict[str, Any] = {}
    logging.debug(f"Loading ctest tests from {file}")

    ctest = which("ctest")
    assert ctest is not None

    with working_dir(os.path.dirname(file)):
        project_binary_dir: str | None = find_project_binary_dir(os.path.dirname(file))
        project_source_dir: str | None = None
        if project_binary_dir is not None:
            project_source_dir = infer_project_source_dir(project_binary_dir)

        try:
            with open(".ctest-json-v1.json", "w") as fh:
                args = [ctest, "--show-only=json-v1"]
                if ctest_config := config.getoption("ctest_config"):
                    args.extend(["-C", ctest_config])
                p = subprocess.Popen(args, stdout=fh)
                p.wait()
            with open(".ctest-json-v1.json", "r") as fh:
                payload = json.load(fh)
        finally:
            force_remove(".ctest-json-v1.json")

        nodes = payload["backtraceGraph"]["nodes"]
        files = payload["backtraceGraph"]["files"]
        for test in payload["tests"]:
            if "command" not in test:
                # this test does not define a command
                continue
            t = tests.setdefault(test["name"], {})
            t["properties"] = test["properties"]
            t["command"] = test["command"]
            t["file"] = os.path.abspath(file)

            # Determine where this test is defined
            t["ctestfile"] = None
            if nodes and project_source_dir is not None and project_binary_dir is not None:
                node = nodes[test["backtrace"]]
                while True:
                    if "parent" not in node:
                        break
                    node = nodes[node["parent"]]
                f = os.path.abspath(files[node["file"]])
                if os.access(f, os.R_OK):
                    # With the CMakeList we can infer the CTest file if we can find the project
                    # source directory
                    reldir = os.path.relpath(os.path.dirname(f), project_source_dir)
                    f = os.path.join(project_binary_dir, reldir, "CTestTestfile.cmake")
                    if os.path.exists(f):
                        t["ctestfile"] = f
            if t["ctestfile"] is None or not os.path.exists(t["ctestfile"]):
                for prop in t["properties"]:
                    if prop["name"] == "WORKING_DIRECTORY":
                        working_directory = prop["value"]
                        f = os.path.join(working_directory, "CTestTestfile.cmake")
                        if os.path.exists(f):
                            # Assume that this test is defined in this file (which is not a guarantee)
                            t["ctestfile"] = os.path.abspath(f)
                            break
            if t["ctestfile"] is None or not os.path.exists(t["ctestfile"]):
                t["ctestfile"] = file

            assert os.path.exists(t["ctestfile"]), "CTestTestfile.cmake not found"

    return tests


def find_project_binary_dir(start: str) -> str | None:
    dirname = start
    while True:
        cmakecache = os.path.join(dirname, "CMakeCache.txt")
        if os.path.exists(cmakecache):
            return dirname
        dirname = os.path.dirname(dirname)
        if dirname == os.path.sep:
            break
    return None


def infer_project_source_dir(project_binary_dir: str) -> str | None:
    f = os.path.join(project_binary_dir, "CMakeCache.txt")
    cache = open(f, "r").read()
    if match := re.search(r"(?im)^\s*CMAKE_PROJECT_NAME.*=(.*)", cache):
        name = match.group(1)
        if match := re.search(r"(?im)^\s*%s_SOURCE_DIR.*=(.*)" % name, cache):
            return match.group(1)
    return None


def find_cmake():
    cmake = which("cmake")
    if cmake is None:
        return None
    out = subprocess.check_output([cmake, "--version"]).decode("utf-8")
    parts = [_.strip() for _ in out.split() if _.split()]
    if parts and parts[0:2] == ["cmake", "version"]:
        version_parts = tuple([int(_) for _ in parts[2].split(".")])
        if version_parts[:2] <= (3, 20):
            logging.warning("canary ctest integration requires cmake > 3.20")
            return None
        return cmake
    return None


def file_contains(file, pattern) -> bool:
    with open(file, "r") as fh:
        for line in fh:
            if re.search(pattern, line):
                return True
    return False


def parse_resource_groups(resource_groups: list[dict[str, list]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for rg in resource_groups:
        group: list[dict[str, Any]] = []
        for requirement in rg["requirements"]:
            type, slots = requirement[".type"], requirement["slots"]
            group.append({"type": type, "slots": slots})
        groups.append(group)
    return groups


def parse_environment(environment: list[str]) -> dict[str, str]:
    """Convert the CTest ENVIRONMENT list[str] to dict[str, str]:

    ["name=value", ..., "name=value"] -> {"name": "value", ...}
    """
    env: dict[str, str] = {}
    for item in environment:
        key, value = item.split("=", 1)
        env[key] = value
    return env


def parse_environment_modification(environment_modification: list[str]) -> list[dict[str, str]]:
    """Convert the CTest ENVIRONMENT_MODIFICATION list[str] to list[dict]:

    ["name=op:value", ..., "name=op:value"] -> [{"name": "name", "op": "op", "value": "value", ...}]
    """
    envmod: list[dict[str, str]] = []
    for item in environment_modification:
        if match := re.search("([^=]+)=([a-z_]+):(.*)", item):
            name, op, value = match.group(1), match.group(2), match.group(3)
            envmod.append({"name": name, "op": op, "value": value})
    return envmod


@hookimpl
def canary_testcase_generator() -> Type[CTestTestGenerator]:
    return CTestTestGenerator


@hookimpl
def canary_configure(config: "Config"):
    setattr(config.test, "timeout_ctest", 1500.0)


@hookimpl
def canary_addoption(parser) -> None:
    parser.add_argument(
        "--ctest-config",
        metavar="cfg",
        group="ctest options",
        command=["run", "find"],
        help="Choose configuration to test",
    )
    parser.add_argument(
        "--ctest-test-timeout",
        metavar="T",
        type=time_in_seconds,
        group="ctest options",
        command="run",
        help="Timeout for ctest tests [default: 1500 s.]",
    )
    parser.add_argument(
        "--recurse-ctest",
        default=None,
        action="store_true",
        group="ctest options",
        command=["run", "find"],
        help="Recurse CMake binary directory for test files.  CTest tests can be detected "
        "from the root CTestTestfile.cmake, so this is option is not necessary unless there "
        "is a mix of CTests and other test types in the binary directory",
    )
