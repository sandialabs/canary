import argparse
import io
import json
import os
import re
import subprocess
from typing import Optional

import nvtest
from _nvtest.test.case import TestCase
from _nvtest.test.generator import TestGenerator
from _nvtest.util import graph
from _nvtest.util import logging
from _nvtest.util.filesystem import is_exe
from _nvtest.util.resource import ResourceInfo

build_types: dict[str, str] = {}


class CTestTestFile(TestGenerator):
    file_type = "CTestTestfile.cmake"

    def __init__(self, root: str, path: Optional[str] = None) -> None:
        super().__init__(root, path=path)

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
        devices: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timelimit: Optional[float] = None,
        owners: Optional[set[str]] = None,
    ) -> list[TestCase]:
        cmake = self.find_cmake()
        if cmake is None:
            return []
        tests = self.parse()
        cases = [CTestTestCase(self.root, self.path, name, **td) for name, td in tests.items()]
        return cases  # type: ignore

    def describe(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        resourceinfo: Optional[ResourceInfo] = None,
    ) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write("Keywords: unit, ctest\n")
        resourceinfo = resourceinfo or ResourceInfo()
        cases = self.freeze(
            cpus=resourceinfo["test:cpus"],
            devices=int(resourceinfo["test:devices"]),
            on_options=on_options,
            keyword_expr=keyword_expr,
        )
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()

    def parse(self) -> dict:
        build_type = find_build_type(os.path.dirname(self.file))
        tests: dict = {}
        with nvtest.filesystem.working_dir(os.path.dirname(self.file)):
            try:
                with open(".nvtest.cmake", "w") as fh:
                    if build_type:
                        fh.write(f"set(CTEST_CONFIGURATION_TYPE {build_type})\n")
                    fh.write(
                        r"""
macro(add_test NAME)
  message("{\"name\": \"${NAME}\", \"args\": \"${ARGN}\"}")
endmacro()

macro(subdirs)
  # Ignore subdirs since we just crawl looking for CTest files
endmacro()

macro(set_tests_properties NAME TITLE)
  set(properties)
  if(${TITLE} STREQUAL "PROPERTIES")
    foreach(ARG ${ARGN})
      if("${ARG}" MATCHES "^_.*")
        break()
      endif()
      list(APPEND properties "${ARG}")
    endforeach()
    message("{\"name\": \"${NAME}\", \"properties\": \"${properties}\"}")
  else()
    message(WARNING "Unknown TITLE ${TITLE}")
  endif()
endmacro()
"""
                    )
                    fh.write(open(self.file).read())
                cmake = self.find_cmake()
                p = subprocess.Popen(
                    [cmake, "-P", ".nvtest.cmake"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                p.wait()
                out, err = p.communicate()
                lines = [l.strip() for l in out.decode("utf-8").split("\n") if l.split()]
                lines.extend([l.strip() for l in err.decode("utf-8").split("\n") if l.split()])
                for line in lines:
                    fd = json.loads(line)
                    if "properties" in fd:
                        props = fd.pop("properties")
                        fd["properties"] = dict(zip(props[0::2], props[1::2]))
                    if "args" in fd:
                        fd["args"] = [_.strip() for _ in fd["args"].split(";") if _.split()]
                    d = tests.setdefault(fd.pop("name"), {})
                    d.update(fd)
            finally:
                nvtest.filesystem.force_remove(".nvtest.cmake")
        return tests


class CTestTestCase(TestCase):
    def __init__(
        self,
        root: str,
        path: str,
        name: str,
        *,
        args: list[str],
        WORKING_DIRECTORY: Optional[str] = None,
        WILL_FAIL: Optional[str] = None,
        TIMEOUT: Optional[str] = None,
        **kwds,
    ) -> None:
        directory = os.path.join(root, os.path.dirname(path))
        with nvtest.filesystem.working_dir(directory):
            ns = parse_test_args(args)
        super().__init__(
            root,
            path,
            family=name,
            keywords=["unit", "ctest"],
            timeout=float(TIMEOUT or 10),
            xstatus=0 if not WILL_FAIL else -1,
            sources={"link": [(ns.command, os.path.basename(ns.command))]},
        )
        self.launcher = ns.launcher
        self.preflags = ns.preflags
        self.command = ns.command
        self.postflags = ns.postflags
        self._processors: int = 1
        if self.preflags:
            self._processors = parse_np(self.preflags)

    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)

    @property
    def processors(self) -> int:
        return self._processors


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
