import argparse
import importlib.resources as ir
import io
import json
import os
import re
import subprocess
from typing import Any
from typing import Optional

import nvtest
from _nvtest.generator import AbstractTestGenerator
from _nvtest.resource import ResourceHandler
from _nvtest.test.case import TestCase
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.filesystem import is_exe


class CTestTestFile(AbstractTestGenerator):
    def __init__(self, root: str, path: Optional[str] = None) -> None:
        super().__init__(root, path=path)

    @classmethod
    def matches(cls, path: str) -> bool:
        return os.path.basename(path) == "CTestTestfile.cmake"

    @staticmethod
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

    def lock(
        self,
        cpus: Optional[list[int]] = None,
        gpus: Optional[list[int]] = None,
        nodes: Optional[list[int]] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timeout: Optional[float] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> list[TestCase]:
        cmake = self.find_cmake()
        if cmake is None:
            logging.warning("cmake not found, test cases cannot be generated")
            return []
        tests = self.parse()
        cases = [
            CTestTestCase(file_root=self.root, file_path=self.path, family=family, **td)
            for family, td in tests.items()
        ]
        return cases  # type: ignore

    def describe(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        rh = rh or ResourceHandler()
        cases = self.lock(
            cpus=rh["test:cpu_count"],
            gpus=rh["test:gpu_count"],
            nodes=rh["test:node_count"],
            on_options=on_options,
            keyword_expr=keyword_expr,
            parameter_expr=parameter_expr,
        )
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def parse(self) -> dict:
        build_type = find_build_type(os.path.dirname(self.file))
        cmake_helper = ir.files("_nvtest").joinpath("plugins/nvtest_ctest/parser.cmake")
        tests: dict = {}
        with nvtest.filesystem.working_dir(os.path.dirname(self.file)):
            try:
                with open(".nvtest.cmake", "w") as fh:
                    if build_type:
                        fh.write(f"set(CTEST_CONFIGURATION_TYPE {build_type})\n")
                    fh.write(cmake_helper.read_text())
                    fh.write(open(self.file).read())
                cmake = self.find_cmake()
                p = subprocess.Popen(
                    [cmake, "-P", ".nvtest.cmake"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                p.wait()
                out, err = p.communicate()
                lines = [l.strip() for l in out.decode("utf-8").split("\n") if l.split()]
                lines.extend([l.strip() for l in err.decode("utf-8").split("\n") if l.split()])
                for line in lines:
                    fd = json.loads(line)
                    if "test" in fd:
                        td = tests.setdefault(fd["test"].pop("name"), {})
                        args = td.setdefault("args", [])
                        if "args" in fd["test"]:
                            a = cmsplit(fd["test"]["args"])
                            if a[0] != cmake:
                                args.extend(a)
                            else:
                                args.append(a[0])
                                args.extend(parse_cmcmdline(";".join(a[1:])))

                    elif "properties" in fd:
                        td = tests.setdefault(fd["properties"].pop("name"), {})
                        for key, details in fd["properties"].items():
                            val: Any
                            type = details["type"]
                            raw_value = details["value"]
                            if type == "str":
                                val = raw_value
                            elif type == "list_of_str":
                                val = cmsplit(raw_value)
                            elif type == "bool":
                                val = cmbool(raw_value)
                            elif type == "int":
                                val = int(raw_value)
                            elif type == "float":
                                val = float(raw_value)
                            elif type == "list_of_var":
                                val = split_vars(raw_value)
                            else:
                                logging.warning(f"Unknown CTest property type: {type}")
                                continue
                            td[key] = val
            finally:
                nvtest.filesystem.force_remove(".nvtest.cmake")
        return tests


def cmbool(string: str) -> bool:
    return string.lower() in ("1", "on", "true", "yes")


def cmsplit(string: str) -> list[str]:
    return [_.strip() for _ in string.split(";") if _.split()]


def parse_cmcmdline(cmdline: str) -> list[str]:
    """Parse the CMake command line generated by add_test

    Some tests are of the form:

    .. code-block:: cmake

       add_test(NAME <name> COMMAND cmake -DOPTION=VAL1;VAL2 -DSPAM=BAZ -P FILE)

    which is transmitted to nvtest as ``cmake;-DOPTION=VAL1;VAL2;-DSPAM=BAZ;-P;FILE``

    We can't simply split on `;` because some options may be lists.

    """
    flags = ("-D", "-P")

    def find(arg: str) -> int:
        indices: list[int] = []
        for flag in flags:
            if (j := arg.find(flag)) != -1:
                indices.append(j)
        if indices:
            return min(indices)
        return -1

    args: list[str] = []
    while True:
        cmdline = cmdline.strip().strip(";")
        if not cmdline.split():
            break
        for flag in flags:
            if cmdline.startswith(flag):
                i = len(flag)
                j = find(cmdline[i:])
                if j == -1:
                    # No other flags, consume until the end of the line
                    if cmdline[i] == ";":
                        args.extend((flag, cmdline[i + 1 :]))
                    else:
                        args.append(cmdline)
                    cmdline = ""
                else:
                    # Consume until next flag
                    if cmdline[i] == ";":
                        args.extend((flag, cmdline[i + 1 : j + 1]))
                    else:
                        args.append(cmdline[: j + 1])
                    cmdline = cmdline[j + 1 :]
                break
        else:
            raise ValueError(f"Unknown CMake flag at {cmdline!r}")
    return args


def split_vars(string: str) -> dict[str, str]:
    vars: dict[str, str] = {}
    for kv in cmsplit(string):
        k, v = kv.split("=", 1)
        vars[k] = v
    return vars


class CTestTestCase(TestCase):
    def __init__(
        self,
        *,
        file_root: Optional[str] = None,
        file_path: Optional[str] = None,
        family: Optional[str] = None,
        args: Optional[list[str]] = None,
        working_directory: Optional[str] = None,
        will_fail: Optional[bool] = None,
        timeout: Optional[float] = None,
        environment: Optional[dict[str, str]] = None,
        labels: Optional[list[str]] = None,
        processors: Optional[int] = None,
        resource_groups: Optional[list[str]] = None,
        **kwds,
    ) -> None:
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            keywords=labels,
            timeout=timeout or 10.0,
        )

        self._resource_groups: Optional[list[str]] = None

        if args is not None:
            directory = os.path.join(self.file_root, os.path.dirname(self.file_path))
            with nvtest.filesystem.working_dir(directory):
                ns = parse_test_args(args)

            self.sources = {"link": [(ns.command, os.path.basename(ns.command))]}
            self.launcher = ns.launcher
            self.preflags = ns.preflags
            self.exe = ns.command
            self.postflags = ns.postflags

        if will_fail:
            self.xstatus = -1

        if "unit" not in self.keywords:
            self.keywords.append("unit")
        if "ctest" not in self.keywords:
            self.keywords.append("ctest")

        if processors is not None:
            self.parameters["np"] = processors
        elif self.preflags:
            self.parameters["np"] = parse_np(self.preflags)

        if environment is not None:
            self.add_default_env(**environment)

        if resource_groups is not None:
            self.resource_groups = resource_groups

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

    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)


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


def find_cmake_cache(directory: str) -> Optional[CMakeCache]:
    if directory == os.path.sep:
        return None
    if directory in cmake_caches:
        return cmake_caches[directory]
    file = os.path.join(directory, "CMakeCache.txt")
    if os.path.exists(file):
        cmake_caches[directory] = CMakeCache(file)
        return cmake_caches[directory]
    return find_cmake_cache(os.path.dirname(directory))


def find_build_type(directory: str) -> Optional[str]:
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
    if not is_exe(arg):
        logging.warning(f"{arg}: ctest command not found")
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
