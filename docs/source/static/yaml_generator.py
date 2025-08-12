import io
import os
import re
from itertools import product
from string import Template
from typing import Any

import yaml

import canary


class YAMLTestGenerator(canary.AbstractTestGenerator):
    """Define a YAML defined test case with the following schema:

    .. code-block:: yaml

       tests:

         str:
           description: str
           script: list[str]
           keywords: list[str]
           parameters: dict[str, list[float | int | str | None]]

    """

    @classmethod
    def matches(cls, path: str) -> bool:
        """Is ``path`` a YAMLTestGenerator?"""
        return re.match("test_.*\.yaml", os.path.basename(path)) is not None

    def lock(self, on_options: list[str] | None = None) -> list[canary.TestCase]:
        """Take the cartesian product of parameters and from each combination create a test case."""

        with open(self.file, "r") as fh:
            fd = yaml.safe_load(fh)

        cases: list[canary.TestCase] = []
        for name, details in fd["tests"].items():
            kwds = dict(
                file_root=self.root,
                file_path=self.path,
                family=name,
                script=details["script"],
                keywords=details.get("keywords", []),
                description=details.get("description"),
            )

            if "parameters" not in details:
                case = YAMLTestCase(**kwds)
                cases.append(case)
                continue

            parameters = details.get("parameters", {})
            keys = list(parameters.keys())
            for values in product(*parameters.values()):
                params = dict(zip(keys, values))
                case = YAMLTestCase(parameters=params, **kwds)
                cases.append(case)
        return cases  # type: ignore

    def describe(self, on_options: list[str] | None = None) -> str:
        cases = self.lock(on_options=on_options)
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"{len(cases)} test cases:\n")
        canary.graph.print(cases, file=file)
        return file.getvalue()


class YAMLTestCase(canary.TestCase):
    def __init__(
        self,
        *,
        file_root: str,
        file_path: str,
        family: str,
        script: list[str],
        keywords: list[str] = [],
        description: str = "",
        parameters: dict[str, Any] = {},
        **kwds,
    ) -> None:
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            parameters=parameters,
        )

        if keywords is not None:
            self.keywords = keywords

        self.scriptname = "test_script.sh"
        self.description = description

        # Expand variables in the script using my parameters
        self.script: list[str] = []
        for line in script:
            t = Template(line)
            self.script.append(t.safe_substitute(**parameters))

    def setup(self) -> None:
        super().setup()
        with canary.filesystem.working_dir(self.working_directory):
            with open(self.scriptname, "w") as fh:
                fh.write("#!/usr/bin/env bash\n")
                fh.write("\n".join(self.script))
            canary.filesystem.set_executable(self.scriptname)

    def command(self) -> list[str]:
        return ["bash", self.scriptname]


@canary.hookimpl
def canary_generator(root: str, path: str | None) -> canary.AbstractTestGenerator:
    if YAMLTestGenerator.matches(root if path is None else os.path.join(root, path)):
        return YAMLTestGenerator(root=root, path=path)
    return None
