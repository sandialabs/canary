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
from _nvtest.resources import ResourceHandler
from _nvtest.test.case import TestCase
from _nvtest.test.generator import TestGenerator
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.filesystem import is_exe

build_types: dict[str, str] = {}


class CTestTestFile(TestGenerator):
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

    def freeze(
        self,
        cpus: Optional[list[int]] = None,
        gpus: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timelimit: Optional[float] = None,
        owners: Optional[set[str]] = None,
    ) -> list[TestCase]:
        cmake = self.find_cmake()
        if cmake is None:
            logging.warning("cmake not found, test cases cannot be generated")
            return []
        tests = self.parse()
        cases = [CTestTestCase(self.root, self.path, name, **td) for name, td in tests.items()]
        return cases  # type: ignore

    def describe(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        rh = rh or ResourceHandler()
        cases = self.freeze(
            cpus=rh["test:cpus"],
            gpus=int(rh["test:gpus"]),
            on_options=on_options,
            keyword_expr=keyword_expr,
        )
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def parse(self) -> dict:
        build_type = find_build_type(os.path.dirname(self.file))
        cmake_helper = ir.files("nvtest").joinpath("plugins/ctest_helpers.cmake")
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
                                args.extend(group_cmargs(";".join(a[1:])))

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
                                val = boolean(raw_value)
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


def boolean(string: str) -> bool:
    return string.lower() in ("1", "on", "true", "yes")


def cmsplit(string: str) -> list[str]:
    return [_.strip() for _ in string.split(";") if _.split()]


def group_cmargs(string: str) -> list[str]:
    p = None
    parts = string.split("-P")
    p = None if len(parts) == 1 else parts[1].strip(";")
    parts = parts[0].split("-D")
    args = [f"-D{_.strip(';')}" for _ in parts if _.split()]
    if p:
        args.extend(("-P", p))
    return args


def split_vars(string: str) -> dict[str, str]:
    vars: dict[str, str] = {}
    for kv in cmsplit(string):
        k, v = kv.split("=")
        vars[k] = v
    return vars


class CTestTestCase(TestCase):
    def __init__(
        self,
        root: str,
        path: str,
        name: str,
        *,
        args: list[str],
        working_directory: Optional[str] = None,
        will_fail: Optional[bool] = False,
        timeout: float = 10.0,
        environment: Optional[dict[str, str]] = None,
        labels: Optional[list[str]] = None,
        processors: Optional[int] = None,
        resource_groups: Optional[list[str]] = None,
        **kwds,
    ) -> None:
        directory = os.path.join(root, os.path.dirname(path))
        with nvtest.filesystem.working_dir(directory):
            ns = parse_test_args(args)

        keywords = ["unit", "ctest"]
        if labels:
            keywords.extend(labels)

        super().__init__(
            root,
            path,
            family=name,
            keywords=keywords,
            timeout=timeout,
            xstatus=0 if not will_fail else -1,
            sources={"link": [(ns.command, os.path.basename(ns.command))]},
        )
        self.launcher = ns.launcher
        self.preflags = ns.preflags
        self.command = ns.command
        self.postflags = ns.postflags
        self._processors: int = 1
        if processors:
            self._processors = processors
        elif self.preflags:
            self._processors = parse_np(self.preflags)
        if environment:
            for var, val in environment.items():
                self.add_default_env(var, val)

        self._gpus: int = 0
        if resource_groups:
            self.read_resource_groups(resource_groups)

    def read_resource_groups(self, resource_groups: list[str]) -> None:
        for rg in resource_groups:
            groups = rg.split(",")
            n = 1
            if match := re.search(r"[0-9]+", groups[0]):
                n = int(match.group(0))
                groups = groups[1:]
            for group in groups:
                if group.startswith("gpus:"):
                    self._gpus += int(group[5:]) * n

    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)

    @property
    def processors(self) -> int:
        return self._processors

    @property
    def gpus(self) -> int:
        return self._gpus


def find_build_type(directory) -> Optional[str]:
    if directory == os.path.sep:
        return None
    if directory in build_types:
        return build_types[directory]
    if os.path.exists(os.path.join(directory, "CMakeCache.txt")):
        with open(os.path.join(directory, "CMakeCache.txt")) as fh:
            for line in fh:
                if line.strip().startswith("CMAKE_BUILD_TYPE"):
                    _, build_type = line.split("=")
                    build_types[directory] = build_type
                    return build_type
    return find_build_type(os.path.dirname(directory))


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


nvtest.plugin.test_generator(CTestTestFile)
