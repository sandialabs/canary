import io
import json
import os
import subprocess
from typing import Optional

import nvtest
from _nvtest.test.case import TestCase
from _nvtest.test.generator import TestGenerator
from _nvtest.util import graph
from _nvtest.util.resource import ResourceInfo

build_types: dict[str, str] = {}


class CTestTestFile(TestGenerator):
    file_type = "CTestTestfile.cmake"

    def __init__(self, root: str, path: Optional[str] = None) -> None:
        super().__init__(root, path=path)

    def freeze(
        self,
        avail_cpus: Optional[int] = None,
        avail_devices: Optional[int] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timelimit: Optional[float] = None,
        owners: Optional[set[str]] = None,
    ) -> list[TestCase]:
        cmake = nvtest.filesystem.which("cmake")
        if cmake is None:
            return []
        tests = self.parse()
        root, path = os.path.split(self.file)
        cases = [CTestTestCase(root, path, name, **td) for name, td in tests.items()]
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
            avail_cpus=int(resourceinfo["test:cpus"]),
            avail_devices=int(resourceinfo["test:devices"]),
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
                    fh.write(cmake_script)
                    fh.write("\n")
                    fh.write(open(self.file).read())
                p = subprocess.Popen(
                    ["cmake", "-P", ".nvtest.cmake"],
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
        command: str,
        args: Optional[list[str]] = None,
        WORKING_DIRECTORY: Optional[str] = None,
        WILL_FAIL: Optional[str] = None,
        TIMEOUT: Optional[str] = None,
        **kwds,
    ) -> None:
        super().__init__(
            root,
            path,
            family=name,
            keywords=["unit", "ctest"],
            timeout=float(TIMEOUT or 10),
            xstatus=0 if not WILL_FAIL else -1,
            sources={"link": [(command, os.path.basename(command))]},
        )
        self.command = command
        self.default_args = list(args or [])

    def command_line_args(self, *args: str) -> list[str]:
        command_line_args = list(self.default_args)
        command_line_args.extend(args)
        return command_line_args


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


nvtest.plugin.test_generator(CTestTestFile)


cmake_script = r"""
macro(add_test NAME COMMAND)
  message("{\"name\": \"${NAME}\", \"command\": \"${COMMAND}\", \"args\": \"${ARGN}\"}")
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
