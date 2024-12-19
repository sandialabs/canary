import argparse
import copy
import io
import json
import os
import re
import shlex
import subprocess
from contextlib import contextmanager
from typing import Any
from typing import Generator

import nvtest
from _nvtest import config
from _nvtest import plugin
from _nvtest.generator import AbstractTestGenerator
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
            dir = os.path.dirname(os.path.abspath(path))
            for no_recurse_dir in CTestTestFile.no_recurse_dirs:
                if dir.startswith(no_recurse_dir):
                    # ctest does its own recursion, following add_directory(...) commands
                    logging.debug(f"CTest: skipping {path} due to ctest recursion")
                    return False
            CTestTestFile.no_recurse_dirs.add(dir)
            logging.debug(f"CTest: marked {dir} to skip recursion")
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
        for family, details in tests.items():
            path = os.path.relpath(details["ctestfile"], self.root)
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
        cmakelists: str | None = None,
        ctestfile: str | None = None,
        **kwds,
    ) -> None:
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            keywords=labels,
            timeout=timeout or 60.0,
        )

        self._resource_groups: list[list[dict[str, Any]]] | None = None
        self._required_files: list[str] | None = None
        self._will_fail: bool = will_fail or False
        self._cmakelists = cmakelists
        self._ctestfile = ctestfile
        self.ctest_working_directory = working_directory

        if command is not None:
            with nvtest.filesystem.working_dir(self.execution_directory):
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

    @property
    def file(self) -> str:
        if self.cmakelists and os.path.exists(self.cmakelists):
            return self.cmakelists
        return self.ctestfile

    @property
    def ctestfile(self) -> str:
        assert self._ctestfile is not None
        return self._ctestfile

    @ctestfile.setter
    def ctestfile(self, arg: str) -> None:
        self._ctestfile = arg

    @property
    def cmakelists(self) -> str | None:
        return self._cmakelists

    @cmakelists.setter
    def cmakelists(self, arg: str) -> None:
        self._cmakelists = arg

    def chain(self, start: str | None = None, anchor: str = ".git") -> str:
        return super().chain(start=self.ctestfile, anchor="CMakeFiles")

    @property
    def execution_directory(self) -> str:
        if self.ctest_working_directory is not None:
            return self.ctest_working_directory
        return self.binary_dir

    @property
    def binary_dir(self) -> str:
        return os.path.dirname(self.ctestfile)

    def required_resources(self) -> list[list[dict[str, Any]]]:
        required = copy.deepcopy(self.resource_groups)
        if not required:
            cpus = self.parameters.get("cpus", 1)
            group = [{"type": "cpus", "slots": 1} for _ in range(cpus)]
            return [group]
        for group in required:
            for item in group:
                if item["type"] == "cpus":
                    break
            else:
                # fill in default cpus required
                cpus = self.parameters.get("cpus", 1)
                group.extend([{"type": "cpus", "slots": 1} for _ in range(cpus)])
        return required

    @property
    def implicit_keywords(self) -> list[str]:
        kwds = super().implicit_keywords
        if "unit" not in kwds:
            kwds.append("unit")
        if "ctest" not in kwds:
            kwds.append("ctest")
        return list(kwds)

    def command(self, stage: str = "run") -> list[str]:
        return [os.path.join(self.working_directory, "runtest")]

    def _command(self) -> list[str]:
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
        os.environ["CTEST_RESOURCE_GROUP_COUNT"] = str(len(self.resources))
        # some resources may have been added to the required resources even if they aren't in the
        # resource groups (eg, cpus).  make sure to remove them so they don't unexpectedly appear
        # in the environment variables
        resource_group_types = {_["type"] for group in self.resource_groups for _ in group}
        for i, spec in enumerate(self.resources):
            types = sorted(resource_group_types & spec.keys())
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

    def setup(self, clean: bool = True) -> None:
        super().setup()
        with nvtest.filesystem.working_dir(self.working_directory):
            sh = nvtest.filesystem.which("sh")
            with open("runtest", "w") as fh:
                fh.write(f"#!{sh}\n")
                fh.write(f"cd {self.execution_directory}\n")
                fh.write(shlex.join(self._command()))
            nvtest.filesystem.set_executable("runtest")

    def finalize(self, stage: str = "run") -> None:
        if stage != "run":
            return

        for hook in plugin.hooks():
            hook.test_after_run(self)

        self.update_run_stats()
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
            t["file"] = os.path.abspath(file)
            if nodes:
                node = nodes[test["backtrace"]]
                t["cmakelists"] = os.path.abspath(files[node["file"]])
            else:
                t["cmakelists"] = None
    logging.debug(f"Found {len(tests)} in {file}")
    return tests


def find_project_binary_dir(file: str) -> str:
    dirname = os.path.dirname(file)
    while True:
        cmakecache = os.path.join(dirname, "CMakeCache.txt")
        if os.path.exists(cmakecache):
            return dirname
        dirname = os.path.dirname(dirname)
        if dirname == os.path.sep:
            break
    return os.path.dirname(file)


def find_project_source_dir(file: str) -> str:
    dirname, basename = os.path.split(os.path.abspath(file))
    if basename not in ("CMakeLists.txt", "CTestTestfile.cmake"):
        logging.warning(f"Unrecognized file name {basename!r}")
    while True:
        parent = os.path.dirname(dirname)
        if not os.path.exists(os.path.join(parent, basename)):
            return dirname
        dirname = parent
        if dirname == os.path.sep:
            break
    return os.path.dirname(os.path.abspath(file))


def transform(tests: dict[str, Any]) -> None:
    """Transform the tests loaded from CMake into a form understood by nvtest

    ``tests`` is of the form

    ``{NAME: {'command': [...], 'properties': [{'name': ..., 'value': ...}, ...]}, ...}``

    and is transformed in place to the form:

    ``{NAME: {'command': [...], 'prop_name': prop_value, ...}, ...}``

    """
    for name, data in tests.items():
        transformed: dict[str, Any] = {"command": data["command"]}
        file = data["file"]
        if data["cmakelists"] is not None:
            cmakelists = data["cmakelists"]
            project_binary_dir = find_project_binary_dir(file)
            project_source_dir = find_project_source_dir(cmakelists)
            reldir = os.path.relpath(os.path.dirname(cmakelists), project_source_dir)
            transformed["project_binary_dir"] = project_binary_dir
            transformed["project_source_dir"] = project_source_dir
            transformed["binary_dir"] = os.path.join(project_binary_dir, reldir)
            transformed["ctestfile"] = os.path.join(
                transformed["binary_dir"], os.path.basename(file)
            )
            transformed["cmakelists"] = cmakelists
            transformed["source_dir"] = os.path.dirname(cmakelists)
        else:
            transformed["ctestfile"] = transformed["cmakelists"] = file
            transformed["project_binary_dir"] = transformed["binary_dir"] = os.path.dirname(file)
            transformed["project_source_dir"] = transformed["source_dir"] = os.path.dirname(file)
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
