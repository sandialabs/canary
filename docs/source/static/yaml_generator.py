import io
import os
from itertools import product
from string import Template
from typing import IO
from typing import Any
from typing import Optional

import nvtest
import yaml
from _nvtest.util import graph
from _nvtest.util.filesystem import set_executable
from _nvtest.util.filesystem import working_dir


class YAMLTestFile(nvtest.AbstractTestGenerator):
    def __init__(self, root: str, path: Optional[str] = None) -> None:
        super().__init__(root, path=path)
        self.load(open(self.file))

    @classmethod
    def matches(cls, path: str) -> bool:
        """Is ``path`` a YAMLTestFile?"""
        return os.path.basename(path).startswith("test_") and path.endswith((".yml", ".yaml"))

    def load(self, file: IO[Any]) -> None:
        """Load the file.  A file may contain more than one test spec

        The test spec has the form:

        .. code-block:: yaml

           NAME:
             description: str
             script: list[str]
             keywords: list[str]
             parameters: dict[str, list[float | int | str | None]]

        """
        self.spec: dict[str, Any] = {}
        data = yaml.safe_load(file)
        if not isinstance(data, dict):
            raise ValueError(f"{file.name}: expected test spec to be a mapping")
        if len(data) != 1:
            raise ValueError(f"{file.name}: expected one test spec")
        self.name = next(iter(data))
        details = data[self.name]
        self.description = details.get("description")
        self.keywords = details.get("keywords", [])
        self.parameters = details.get("parameters", {})
        self.script = details.get("script", [])

    def lock(self, on_options: Optional[list[str]] = None) -> list[nvtest.TestCase]:
        """Take the cartesian product of parameters and from each combination create a test case."""
        kwds = dict(
            file_root=self.root,
            file_path=self.path,
            family=self.name,
            script=self.script,
            keywords=self.keywords,
            description=self.description,
        )
        if not self.parameters:
            case = YAMLTestCase(**kwds)
            return [case]
        cases: list[YAMLTestCase] = []
        keys = list(self.parameters.keys())
        for values in product(*self.parameters.values()):
            parameters = dict(zip(keys, values))
            case = YAMLTestCase(parameters=parameters, **kwds)
            cases.append(case)
        return cases  # type: ignore

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


class YAMLTestCase(nvtest.TestCase):
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

        self.launcher = "bash"
        self.exe = "test_script.sh"
        self.description = description

        # Expand variables in the script using my parameters
        self.script: list[str] = []
        for line in script:
            t = Template(line)
            self.script.append(t.safe_substitute(**parameters))

    def setup(self, exec_root: str, copy_all_resources: bool = False) -> None:
        super().setup(exec_root, copy_all_resources=copy_all_resources)
        with working_dir(self.exec_dir):
            with open(self.exe, "w") as fh:
                fh.write("#!/usr/bin/env bash\n")
                fh.write("\n".join(self.script))
            set_executable(self.exe)
