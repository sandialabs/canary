import argparse
import importlib.resources as ir
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
from _nvtest.generator import AbstractTestGenerator
from _nvtest.test.case import TestCase
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.filesystem import is_exe


class CTestTestFile(AbstractTestGenerator):
    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.owners: list[str] = []

    @classmethod
    def matches(cls, path: str) -> bool:
        return os.path.basename(path) == "CTestTestfile.cmake"

    def lock(self, on_options: list[str] | None = None) -> list[TestCase]:
        cmake = find_cmake()
        if cmake is None:
            logging.warning("cmake not found, test cases cannot be generated")
            return []
        tests = self.parse()
        cases: list[TestCase] = []
        for family, td in tests.items():
            case = CTestTestCase(file_root=self.root, file_path=self.path, family=family, **td)
            cases.append(case)
        return cases  # type: ignore

    def describe(self, on_options: list[str] | None = None) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        cases = self.lock(on_options=on_options)
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def parse(self) -> dict:
        build_type = find_build_type(os.path.dirname(self.file))
        tests = parse(self.file, CTEST_CONFIGURATION_TYPE=build_type)
        return tests


class CTestTestCase(TestCase):
    def __init__(
        self,
        *,
        file_root: str | None = None,
        file_path: str | None = None,
        family: str | None = None,
        args: list[str] | None = None,
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
        resource_groups: list[str] | None = None,
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
            timeout=timeout or 10.0,
        )

        self._resource_groups: list[str] | None = None
        self._working_directory = working_directory or self.file_dir

        if args is not None:
            with nvtest.filesystem.working_dir(self.file_dir):
                ns = parse_test_args(args)

            self.sources = {}
            self.launcher = ns.launcher
            self.preflags = ns.preflags
            self.exe = ns.command
            self.postflags = ns.postflags

        if will_fail:
            self.xstatus = -1

        if processors is not None:
            self.parameters["np"] = processors

        elif self.preflags:
            self.parameters["np"] = parse_np(self.preflags)

        if depends:
            self.dep_patterns.extend(depends)

        if environment is not None:
            self.add_default_env(**environment)

        if resource_groups is not None:
            self.resource_groups = resource_groups

        if disabled:
            self.mask = f"Explicitly disabled in {self.file}"

        self.environment_modification = environment_modification
        self.pass_regular_expression = pass_regular_expression
        self.fail_regular_expression = fail_regular_expression
        self.skip_regular_expression = skip_regular_expression
        self.skip_return_code = skip_return_code

        def unsupported_ctest_option(option: str) -> str:
            file = io.StringIO()
            file.write(f"The ctest test property {option.upper()!r} is currently not supported, ")
            file.write("contact the nvtest developers to implement this property")
            return file.getvalue()

        if attached_files is not None:
            logging.warning(unsupported_ctest_option("attached_files"))
        if attached_files_on_fail is not None:
            logging.warning(unsupported_ctest_option("attached_files_on_fail"))
        if cost is not None:
            logging.warning(unsupported_ctest_option("cost"))
        if fixtures_cleanup is not None:
            logging.warning(unsupported_ctest_option("fixtures_cleanup"))
        if fixtures_required is not None:
            logging.warning(unsupported_ctest_option("fixtures_required"))
        if fixtures_setup is not None:
            logging.warning(unsupported_ctest_option("fixtures_setup"))
        if generated_resource_spec_file is not None:
            logging.warning(unsupported_ctest_option("generated_resource_spec_file"))
        if measurement is not None:
            logging.warning(unsupported_ctest_option("measurement"))
        if processor_affinity is not None:
            logging.warning(unsupported_ctest_option("processor_affinity"))
        if required_files is not None:
            logging.warning(unsupported_ctest_option("required_files"))
        if resource_lock is not None:
            logging.warning(unsupported_ctest_option("resource_lock"))
        if run_serial is not None:
            logging.warning(unsupported_ctest_option("run_serial"))
        if timeout_after_match is not None:
            logging.warning(unsupported_ctest_option("timeout_after_match"))
        if timeout_signal_grace_period is not None:
            logging.warning(unsupported_ctest_option("timeout_signal_grace_period"))
        if timeout_signal_name is not None:
            logging.warning(unsupported_ctest_option("timeout_signal_name"))

    @property
    def implicit_keywords(self) -> list[str]:
        kwds = super().implicit_keywords
        if "unit" not in kwds:
            kwds.append("unit")
        if "ctest" not in kwds:
            kwds.append("ctest")
        return list(kwds)

    @property
    def working_directory(self) -> str:
        return self._working_directory

    @working_directory.setter
    def working_directory(self, arg: str) -> None:
        self._working_directory = arg

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        with super().rc_environ():
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

    def setup(self, exec_root: str, copy_all_resources: bool = False) -> None:
        super().setup(exec_root, copy_all_resources=copy_all_resources)
        with nvtest.filesystem.working_dir(self.exec_dir):
            with open("ctest-command.txt", "w") as fh:
                fh.write(" ".join(self.command()))

    def wrap_up(self) -> None:
        super().wrap_up()
        file = self.logfile("test")

        if self.status.value in ("timeout", "skipped", "not_run"):
            return

        if self.skip_regular_expression is not None:
            for skip_regular_expression in self.skip_regular_expression:
                if file_contains(file, skip_regular_expression):
                    self.status.set(
                        "skipped",
                        f"Regular expression {skip_regular_expression!r} found in {file}",
                    )
                    return

        if self.skip_return_code is not None:
            if self.returncode == self.skip_return_code:
                self.status.set("skipped", f"Return code={self.skip_return_code!r}")
                return

        if self.pass_regular_expression is not None:
            for pass_regular_expression in self.pass_regular_expression:
                if file_contains(file, pass_regular_expression):
                    self.status.set("success")
                    return
            self.status.set(
                "failed", f"Regular expression {pass_regular_expression!r} not found in {file}"
            )
            return

        if self.status == "failed":
            return

        if self.fail_regular_expression is not None:
            for fail_regular_expression in self.fail_regular_expression:
                print(0, fail_regular_expression)
                print(1, open(file).read())
                if file_contains(file, fail_regular_expression):
                    self.status.set(
                        "failed", f"Regular expression {fail_regular_expression!r} found in {file}"
                    )
                    return

    @property
    def resource_groups(self) -> list[str]:
        return self._resource_groups or []

    @resource_groups.setter
    def resource_groups(self, arg: list[str]) -> None:
        self._resource_groups = arg
        self.read_resource_groups()

    def read_resource_groups(self) -> None:
        for rg in self.resource_groups:
            groups = rg.split(",")
            n = 1
            if match := re.search(r"[0-9]+", groups[0]):
                n = int(match.group(0))
                groups = groups[1:]
            for group in groups:
                if group.startswith("gpus:"):
                    gpus = self.parameters.setdefault("ngpu", 0)
                    gpus += int(group[5:]) * n
                    self.parameters["ngpu"] = gpus


class CMakeCache(dict):
    def __init__(self, file: str) -> None:
        self.directory = os.path.dirname(os.path.abspath(file))
        with open(file) as fh:
            for line in fh:
                if line.strip().startswith("CMAKE_"):
                    type = "string"
                    var, val = [_.strip() for _ in line.split("=", 1)]
                    if ":" in var:
                        var, type = var.split(":", 1)
                    self[var.replace("CMAKE_", "").lower()] = {"type": type, "value": val}


cmake_caches: dict[str, CMakeCache] = {}


def find_cmake_cache(directory: str) -> CMakeCache | None:
    if directory == os.path.sep:
        return None
    if directory in cmake_caches:
        return cmake_caches[directory]
    file = os.path.join(directory, "CMakeCache.txt")
    if os.path.exists(file):
        cmake_caches[directory] = CMakeCache(file)
        return cmake_caches[directory]
    return find_cmake_cache(os.path.dirname(directory))


def find_build_type(directory: str) -> str | None:
    cache = find_cmake_cache(directory)
    return None if cache is None else cache["build_type"]["value"]


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
            raise ValueError(f"Unable to find test program in {s}")
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


def parse(file, **defs) -> dict[str, Any]:
    parser = ir.files("_nvtest").joinpath("plugins/nvtest_ctest/parser.cmake")
    tests: dict[str, Any] = {}
    with nvtest.filesystem.working_dir(os.path.dirname(file)):
        cmake = find_cmake()
        args = [cmake, f"-DTESTFILE={file}"]
        for key, val in defs.items():
            args.append(f"-D{key}={val}")
        args.append(f"-P{parser}")
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        out, err = p.communicate()
        lines = [l.strip() for l in out.decode("utf-8").split("\n") if l.split()]
        lines.extend([l.strip() for l in err.decode("utf-8").split("\n") if l.split()])
        for line in lines:
            fd = json.loads(line)
            if "test" in fd:
                td = tests.setdefault(fd["test"].pop("name"), {})
                td["args"] = fd["test"].get("args", [])
            elif "properties" in fd:
                td = tests.setdefault(fd["properties"].pop("name"), {})
                td.update(fd["properties"])
    return tests


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
