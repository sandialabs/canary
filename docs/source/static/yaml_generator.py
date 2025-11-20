import io
import os
import re
from itertools import product
from pathlib import Path

import canary
import yaml


@canary.hookimpl
def canary_testcase_generator(root: str, path: str | None) -> "YAMLTestGenerator":
    if YAMLTestGenerator.matches(root if path is None else os.path.join(root, path)):
        return YAMLTestGenerator(root, path)


@canary.hookimpl
def canary_testcase_setup(case: canary.TestCase) -> None:
    if not YAMLTestGenerator.matches(case.spec.file):
        return
    sh = canary.filesystem.which("sh")
    if script := case.attributes.get("script"):
        with case.workspace.openfile("runtest.sh", "w") as fh:
            fh.write(f"#!{sh}\n")
            fh.write(f"cd {case.workspace.dir}\n")
            fh.write("\n".join(script))
        canary.filesystem.set_executable(case.workspace.joinpath("runtest.sh"))
    else:
        raise ValueError(f"{case}: script attribute not found")


@canary.hookimpl
def canary_testcase_execution_policy(case: canary.TestCase) -> canary.ExecutionPolicy | None:
    if YAMLTestGenerator.matches(case.spec.file):
        return canary.SubprocessExecutionPolicy(["./runtest.sh"])
    return None


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
    def matches(cls, path: str | Path) -> bool:
        """Is ``path`` a YAMLTestGenerator?"""
        path = Path(path)
        return re.match("test_.*\.yaml", path.name) is not None

    def lock(self, on_options: list[str] | None = None) -> list[canary.DraftSpec]:
        """Take the cartesian product of parameters and from each combination create a test case."""

        with open(self.file, "r") as fh:
            fd = yaml.safe_load(fh)

        specs: list[canary.DraftSpec] = []
        for name, details in fd["tests"].items():
            kwds = dict(
                file_root=Path(self.root),
                file_path=Path(self.path),
                family=name,
                keywords=details.get("keywords", []),
                attributes={"details": details.get("description"), "script": details["script"]},
            )

            if parameters := details.get("parameters"):
                keys = list(parameters.keys())
                for values in product(*parameters.values()):
                    params = dict(zip(keys, values))
                    spec = canary.DraftSpec(parameters=params, **kwds)
                    specs.append(spec)
            else:
                spec = canary.DraftSpec(**kwds)
                specs.append(spec)

        return specs

    def describe(self, on_options: list[str] | None = None) -> str:
        cases = self.lock(on_options=on_options)
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"{len(cases)} test cases:\n")
        canary.graph.print(cases, file=file)
        return file.getvalue()
