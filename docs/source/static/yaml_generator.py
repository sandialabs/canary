import io
import itertools
import re
from string import Template
from typing import Optional
from typing import Type

import yaml

import canary
from _canary.util import graph
from _canary.util.filesystem import set_executable
from _canary.util.filesystem import working_dir


@canary.hookimpl
def canary_testcase_generator() -> Type["YAMLTestGenerator"]:
    return YAMLTestGenerator


class YAMLTestGenerator(canary.AbstractTestGenerator):
    @classmethod
    def matches(cls, path: str) -> bool:
        return re.match("test_.*\.yaml", path)

    def lock(self, on_options: Optional[list[str]] = None) -> list[canary.TestCase]:
        with open(self.file, "r") as fh:
            fd = yaml.load(fh)
        cases: list[canary.TestCase] = []
        for spec in fd["tests"]:
            parameter_names = list(spec["parameters"].keys())
            for parameter_values in itertools.product(*spec["parameters"].values()):
                parameters = dict(zip(parameter_names, parameter_values))
                script = [Template(cmd).safe_substitute(**parameters) for cmd in spec["script"]]
                case = YAMLTestCase(
                    file_root=self.root,
                    file_path=self.path,
                    family=spec["name"],
                    keywords=spec["keywords"],
                    script=script,
                    parameters=parameters,
                )
                cases.append(case)
        return cases

    def describe(self, on_options: Optional[list[str]] = None) -> str:
        cases = self.lock(on_options=on_options)
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Description: {self.description}\n")
        file.write(f"Keywords: {', '.join(self.keywords)}\n")
        file.write(f"{len(cases)} test cases:\n")
        graph.print(cases, file=file)
        return file.getvalue()


class YAMLTestCase(canary.TestCase):
    def __init__(self, **kwds) -> None:
        self.script = kwds.pop("script")
        super().__init__(**kwds)
        self.launcher = "bash"
        self.exe = "test.sh"

    def setup(self, stage: str = "run", copy_all_resources: bool = False) -> None:
        super().setup(stage=stage, copy_all_resources=copy_all_resources)
        with working_dir(self.working_directory):
            with open(self.exe, "w") as fh:
                fh.write("#!/usr/bin/env bash\n")
                fh.write("\n".join(self.script))
            set_executable(self.exe)
