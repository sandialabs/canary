import argparse
import io
import json
import os
import re
import subprocess
from contextlib import contextmanager
from typing import Any
from typing import Generator
from typing import MutableMapping

import nvtest
from _nvtest import config
from _nvtest.generator import AbstractTestGenerator
from _nvtest.generator import StopRecursion
from _nvtest.test.case import DependencyPatterns
from _nvtest.test.case import TestCase
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import is_exe

warning_cache = set()


def warn_unsupported_ctest_option(option: str) -> None:
    if option in warning_cache:
        return
    file = io.StringIO()
    file.write(f"The ctest test property {option.upper()!r} is currently not supported, ")
    file.write("contact the nvtest developers to implement this property")
    logging.warning(file.getvalue())
    warning_cache.add(option)


class CTestTestFile(AbstractTestGenerator):
    no_recurse_dirs: set[str] = set()

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.owners: list[str] = []

    @classmethod
    def matches(cls, path: str) -> bool:
        matches = cls.always_matches(path)
        if matches:
            if not config.getoption("recurse_cmake"):
                raise StopRecursion
            dir = os.path.dirname(os.path.abspath(path))
            cmakecache = os.path.join(dir, "CMakeCache.txt")
            if os.path.exists(cmakecache):
                # This file is in the root of the binary directory, we don't need to recurse any
                # further since CTest will do that
                CTestTestFile.no_recurse_dirs.add(dir)
                logging.debug(f"CTest: marked {dir} to skip recursion")
                return True
            else:
                for no_recurse_dir in CTestTestFile.no_recurse_dirs:
                    if dir.startswith(no_recurse_dir):
                        # tests in this file should have already been added by cmake
                        logging.debug(f"CTest: skipping {path} due to skipped recursion")
                        return False
                return True
        return False

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
        cmakefiles = sorted([td["file"] for td in tests.values()], key=lambda x: len(x))
        root = os.path.dirname(os.path.abspath(cmakefiles[0]))
        for family, td in tests.items():
            cmakefile = td["file"]
            if os.path.exists(cmakefile):
                path = os.path.relpath(cmakefile, root)
                case = CTestTestCase(file_root=root, file_path=path, family=family, **td)
            else:
                # This happens in unit tests where we use a CTestTestfile.cmake without an
                # associated CMake file
                case = CTestTestCase(file_root=self.root, file_path=self.path, family=family, **td)
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
        tests = load(self.file)
        transform(tests)
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

    @staticmethod
    def resolve_inter_dependencies(cases: list["CTestTestCase"]) -> None:
        logging.debug("Resolving dependencies in test file")
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
        resource_groups: dict[str, int] | None = None,
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
        **kwds,
    ) -> None:
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            keywords=labels,
            timeout=timeout or 60.0,
        )

        self._resource_groups: dict[str, int] | None = None
        self._required_files: list[str] | None = None
        self._will_fail: bool = will_fail or False
        self.working_directory = working_directory or self.file_dir

        if command is not None:
            with nvtest.filesystem.working_dir(self.working_directory):
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
            if "gpus" in self.resource_groups:
                self.parameters["gpus"] = self.resource_groups["gpus"]

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

        self.environment_modification = environment_modification
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

    @property
    def implicit_keywords(self) -> list[str]:
        kwds = super().implicit_keywords
        if "unit" not in kwds:
            kwds.append("unit")
        if "ctest" not in kwds:
            kwds.append("ctest")
        return list(kwds)

    def command(self, stage: str = "run") -> list[str]:
        cmd: list[str] = []
        if self.launcher:
            cmd.append(self.launcher)
            cmd.extend(self.preflags or [])
        cmd.append(self.exe)
        cmd.extend(self.postflags or [])
        return cmd

    @contextmanager
    def rc_environ(self, **variables: str) -> Generator[None, None, None]:
        with super().rc_environ(**variables):
            self.apply_environment_modifications(os.environ)
            yield

    def apply_environment_modifications(self, env: MutableMapping[str, str]) -> None:
        if self.environment_modification is None:
            return
        for em in self.environment_modification:
            op, name, value = em["op"], em["name"], em["value"]
            match op:
                case "set":
                    env[name] = value
                case "unset":
                    env.pop(name, None)
                case "string_append":
                    old = os.getenv(name, "")
                    env[name] = f"{old}{value}"
                case "string_prepend":
                    old = os.getenv(name, "")
                    env[name] = f"{value}{old}"
                case "path_list_append":
                    old = os.getenv(name, "")
                    env[name] = f"{old}:{value}"
                case "path_list_prepend":
                    old = os.getenv(name, "")
                    env[name] = f"{value}:{old}"
                case "cmake_list_append":
                    old = os.getenv(name, "")
                    env[name] = f"{old};{value}"
                case "cmake_list_prepend":
                    old = os.getenv(name, "")
                    env[name] = f"{value};{old}"

    def setup(self, work_tree: str, copy_all_resources: bool = False, clean: bool = True) -> None:
        super().setup(work_tree, copy_all_resources=copy_all_resources, clean=False)
        with nvtest.filesystem.working_dir(self.cache_directory):
            with open("ctest-command.txt", "w") as fh:
                command = " ".join(self.command())
                fh.write(f"cd {self.working_directory} && {command}")

    def setup_working_directory(self, copy_all_resources: bool = False) -> None:
        """CMake sets up the working (binary) directory"""

    def finalize(self, stage: str = "run") -> None:
        self.cache_runtime()
        self.concatenate_logs()
        file = self.logfile(stage)

        if self.status.value in ("timeout", "skipped", "not_run"):
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

        self.save()

    @property
    def resource_groups(self) -> dict[str, int]:
        return self._resource_groups or {}

    @resource_groups.setter
    def resource_groups(self, arg: dict[str, int]) -> None:
        self._resource_groups = arg

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
    with nvtest.filesystem.working_dir(os.path.dirname(file)):
        ctest = nvtest.filesystem.which("ctest")
        assert ctest is not None
        try:
            with open(".ctest-json-v1.json", "w") as fh:
                p = subprocess.Popen([ctest, "--show-only=json-v1"], stdout=fh)
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
            if nodes:
                node = nodes[test["backtrace"]]
                t["file"] = files[node["file"]]
            else:
                t["file"] = os.path.abspath(file)
    logging.debug(f"Found {len(tests)} in {file}")
    return tests


def transform(tests: dict[str, Any]) -> None:
    """Transform the tests loaded from CMake into a form understood by nvtest

    ``tests`` is of the form

    ``{NAME: {'command': [...], 'properties': [{'name': ..., 'value': ...}, ...]}, ...}``

    and is transformed in place to the form:

    ``{NAME: {'command': [...], 'prop_name': prop_value, ...}, ...}``

    """
    for name, data in tests.items():
        transformed = {"command": data["command"], "file": data["file"]}
        for prop in data["properties"]:
            prop_name, prop_value = prop["name"], prop["value"]
            if prop_name == "ENVIRONMENT":
                prop_value = parse_environment(prop_value)
            elif prop_name == "ENVIRONMENT_MODIFICATION":
                prop_value = parse_environment_modification(prop_value)
            elif prop_name == "RESOURCE_GROUPS":
                prop_value = parse_resource_groups(prop_value)
            transformed[prop_name.lower()] = prop_value
        tests[name] = transformed
    return


def find_cmake():
    cmake = nvtest.filesystem.which("cmake")
    if cmake is None:
        return None
    out = subprocess.check_output([cmake, "--version"]).decode("utf-8")
    parts = [_.strip() for _ in out.split() if _.split()]
    if parts and parts[0:2] == ["cmake", "version"]:
        version_parts = tuple([int(_) for _ in parts[2].split(".")])
        if version_parts[:2] <= (3, 20):
            logging.warning("nvtest ctest integration requires cmake > 3.20")
            return None
        return cmake
    return None


def file_contains(file, pattern) -> bool:
    with open(file, "r") as fh:
        for line in fh:
            if re.search(pattern, line):
                return True
    return False


def parse_resource_groups(resource_groups: list[dict[str, list]]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for rg in resource_groups:
        for requirement in rg["requirements"]:
            type, slots = requirement[".type"], requirement["slots"]
            groups[type] = groups.setdefault(type, 0) + slots
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
