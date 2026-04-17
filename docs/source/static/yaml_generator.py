import io
from itertools import product
from pathlib import Path
from string import Template
from typing import ClassVar
from typing import Any

import canary
import schema
import yaml


@canary.hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(YAMLTestGenerator)


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
    file_patterns: ClassVar[tuple[str, ...]] = ("test_*.yaml",)

    def lock(self, on_options: list[str] | None = None) -> list[canary.ResolvedSpec]:
        """Take the cartesian product of parameters and from each combination create a test case."""

        with open(self.file, "r") as fh:
            fd = yaml.safe_load(fh)
        fd = yaml_schema.validate(fd)

        specs: list[canary.ResolvedSpec] = []
        for name, details in fd["tests"].items():
            kwds: dict[str, Any] = dict(
                file_root=Path(self.root),
                file_path=Path(self.path),
                family=name,
                keywords=details.get("keywords", []),
                attributes={"description": details.get("description")},
            )
            script = details["script"]
            sh = canary.filesystem.which("sh", required=True)
            if parameters := details.get("parameters"):
                keys = list(parameters.keys())
                for values in product(*parameters.values()):
                    p = kwds["parameters"] = dict(zip(keys, values))
                    shell_cmds: list[str] = [Template(_).safe_substitute(**p) for _ in script]
                    kwds["command"] = [sh, "-c", "set -e\n" + "\n".join(shell_cmds)]
                    spec = canary.ResolvedSpec(**kwds)
                    specs.append(spec)
            else:
                kwds["command"] = [sh, "-c", "set -e\n" + "\n".join(script)]
                spec = canary.ResolvedSpec(**kwds)
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


yaml_schema = schema.Schema(
    {
        "tests": {
            str: {
                schema.Optional("description", default="Yaml test instance"): str,
                "script": [str],
                schema.Optional("keywords"): [str],
                schema.Optional("parameters"): {str: [schema.Or(int, float, str, type(None))]},
            }
        }
    }
)
