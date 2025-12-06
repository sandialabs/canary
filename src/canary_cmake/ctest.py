# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import schema

import canary

warning_cache = set()

logger = canary.get_logger(__name__)


def warn_unsupported_ctest_option(option: str) -> None:
    if option in warning_cache:
        return
    file = io.StringIO()
    file.write(f"The ctest test property {option.upper()!r} is currently not supported, ")
    file.write("contact the canary developers to implement this property")
    logger.warning(file.getvalue())
    warning_cache.add(option)


class CTestTestGenerator(canary.AbstractTestGenerator):
    def __init__(self, root: str, path: str | None = None) -> None:
        # CTest works with resolved paths
        super().__init__(os.path.abspath(root), path=path)
        self.owners: list[str] = []

    @classmethod
    def matches(cls, path: str) -> bool:
        matches = cls.always_matches(path)
        if matches:
            return True
        return False

    def stop_recursion(self) -> bool:
        if canary.config.getoption("canary_cmake_recurse_ctest", False):
            return False
        return True

    @classmethod
    def always_matches(cls, path: str) -> bool:
        return os.path.basename(path) == "CTestTestfile.cmake"

    def lock(self, on_options: list[str] | None = None) -> list[canary.ResolvedSpec]:
        cmake = find_cmake()
        if cmake is None:
            logger.warning("cmake not found, test cases cannot be generated")
            return []
        tests = self.load()
        if not tests:
            return []
        drafts: list[canary.UnresolvedSpec] = []
        realpath = os.path.realpath
        for family, details in tests.items():
            path = os.path.relpath(details["ctestfile"], self.root)
            if not os.path.exists(os.path.join(self.root, path)):
                path = os.path.relpath(realpath(details["ctestfile"]), realpath(self.root))
            draft = create_draft_spec(
                file_root=self.root,
                file_path=path,
                family=family,
                ctestfile=details.pop("ctestfile"),
                command=details.pop("command"),
                **details,
            )
            drafts.append(draft)
        resolved = self.resolve_inter_dependencies(drafts)
        self.resolve_fixtures(resolved)
        return resolved  # type: ignore

    def describe(self, on_options: list[str] | None = None) -> str:
        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        cases = self.lock(on_options=on_options)
        file.write(f"{len(cases)} test cases:\n")
        canary.graph.print(cases, file=file)
        return file.getvalue()

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = {}
        tests = self.load()
        for details in tests.values():
            info.setdefault("keywords", []).extend(details.get("labels", []))
        return info

    def load(self) -> dict:
        """Load and transform the tests loaded from CMake into a form understood by nvtest

        ``tests`` is of the form

        ``{NAME: {'command': [...], 'properties': [{'name': ..., 'value': ...}, ...]}, ...}``

        and is transformed in place to the form:

        ``{NAME: {'command': [...], 'prop_name': prop_value, ...}, ...}``

        """
        tests = load(self.file)
        if not tests:
            return {}
        for name, defn in tests.items():
            transformed: dict[str, Any] = {"command": defn["command"]}
            transformed["ctestfile"] = defn["ctestfile"] or self.file
            for prop in defn["properties"]:
                prop_name, prop_value = prop["name"], prop["value"]
                if prop_name == "ENVIRONMENT":
                    prop_value = parse_environment(prop_value)
                elif prop_name == "ENVIRONMENT_MODIFICATION":
                    prop_value = parse_environment_modification(prop_value)
                elif prop_name == "RESOURCE_GROUPS":
                    prop_value = parse_resource_groups(prop_value)
                transformed[prop_name.lower()] = prop_value
            tests[name] = transformed
        return tests

    def resolve_fixtures(self, specs: list["canary.ResolvedSpec"]) -> None:
        setup_fixtures: dict[str, list[canary.ResolvedSpec]] = {}
        cleanup_fixtures: dict[str, list[canary.ResolvedSpec]] = {}
        for spec in specs:
            for fixture_name in spec.attributes["fixtures"]["setup"]:
                setup_fixtures.setdefault(fixture_name, []).append(spec)
            for fixture_name in spec.attributes["fixtures"]["cleanup"]:
                cleanup_fixtures.setdefault(fixture_name, []).append(spec)
        for spec in specs:
            for fixture_name in spec.attributes["fixtures"]["required"]:
                if fixture_name in setup_fixtures:
                    for fixture in setup_fixtures[fixture_name]:
                        spec.dependencies.append(fixture)  # type: ignore
                if fixture_name in cleanup_fixtures:
                    for fixture in cleanup_fixtures[fixture_name]:
                        fixture.dependencies.append(spec)  # type: ignore

    def resolve_inter_dependencies(
        self, drafts: list["canary.UnresolvedSpec"]
    ) -> list["canary.ResolvedSpec"]:
        from _canary.build import resolve

        resolved = resolve(drafts)
        return resolved


def create_draft_spec(
    *,
    file_root: str,
    file_path: str,
    family: str,
    command: list[str],
    ctestfile: str,
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
    resource_groups: list[list[dict[str, Any]]] | None = None,
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
) -> canary.UnresolvedSpec:
    kwargs: dict[str, Any] = {}
    kwargs["file_root"] = Path(file_root)
    kwargs["file_path"] = Path(file_path)
    kwargs["family"] = family
    labels = labels or []
    kwargs["keywords"] = ["ctest", *labels]

    attributes: dict[str, Any] = kwargs.setdefault("attributes", {})

    attributes["command"] = command
    attributes["will_fail"] = will_fail or False

    attributes["ctestfile"] = str(ctestfile)
    attributes["ctest_working_directory"] = working_directory
    attributes["binary_dir"] = os.path.dirname(str(ctestfile))
    if working_directory is not None:
        attributes["execution_directory"] = working_directory
    else:
        attributes["execution_directory"] = attributes["binary_dir"]

    if processors is not None:
        kwargs.setdefault("parameters", {})["cpus"] = processors
    elif np := parse_np(command):
        kwargs.setdefault("parameters", {})["cpus"] = np
    if depends:
        deps = kwargs.setdefault("dependencies", [])
        for d in depends:
            deps.append(canary.DependencyPatterns(pattern=d, expects="+", result_match="success"))
    if environment is not None:
        kwargs.setdefault("environment", {}).update(environment)
    if disabled:
        kwargs["mask"] = f"Explicitly disabled in {file_root}/{file_path}"

    attributes.setdefault("resource_groups", [])
    if resource_groups is not None:
        attributes["resource_groups"].extend(resource_groups)
        params: dict[str, float | int] = {}
        for group in resource_groups:
            for item in group:
                params[item["type"]] = params.get(item["type"], 0) + item["slots"]
        kwargs.setdefault("parameters", {}).update(params)

    if attached_files is not None:
        artifacts = kwargs.setdefault("artifacts", [])
        artifacts.extend([{"file": f, "when": "always"} for f in attached_files])
    if attached_files_on_fail is not None:
        artifacts = kwargs.setdefault("artifacts", [])
        artifacts.extend([{"file": f, "when": "on_failure"} for f in attached_files_on_fail])
    if run_serial is True:
        kwargs["exclusive"] = True
    if required_files:
        attributes["required_files"] = required_files
    if environment_modification is not None:
        kwargs["environment_modifications"] = env_mods(environment_modification)

    if timeout is not None:
        kwargs["timeout"] = float(timeout)
    elif var := canary.config.getoption("canary_cmake_test_timeout"):
        kwargs["timeout"] = float(var)
    elif var := os.getenv("CTEST_TEST_TIMEOUT"):
        kwargs["timeout"] = canary.time.time_in_seconds(var)
    elif t := kwds.get("timeout_property"):
        kwargs["timeout"] = float(t)
    else:
        kwargs["timeout"] = canary.config.get("timeout:ctest", 1500.0)

    attributes["pass_regular_expression"] = pass_regular_expression
    attributes["fail_regular_expression"] = fail_regular_expression
    attributes["skip_regular_expression"] = skip_regular_expression
    attributes["skip_return_code"] = skip_return_code

    fixtures: dict[str, list] = attributes.setdefault("fixtures", {})
    cleanup_fixtures = fixtures.setdefault("cleanup", [])
    if fixtures_cleanup:
        cleanup_fixtures.extend(fixtures_cleanup)
    required_fixtures = fixtures.setdefault("required", [])
    if fixtures_required:
        required_fixtures.extend(fixtures_required)
    setup_fixtures = fixtures.setdefault("setup", [])
    if fixtures_setup:
        setup_fixtures.extend(fixtures_setup)
    if cost is not None:
        warn_unsupported_ctest_option("cost")
    if generated_resource_spec_file is not None:
        warn_unsupported_ctest_option("generated_resource_spec_file")
    if measurement is not None:
        warn_unsupported_ctest_option("measurement")
    if processor_affinity:
        warn_unsupported_ctest_option("processor_affinity")
    if resource_lock is not None:
        warn_unsupported_ctest_option("resource_lock")
    if timeout_after_match is not None:
        warn_unsupported_ctest_option("timeout_after_match")
    if timeout_signal_grace_period is not None:
        warn_unsupported_ctest_option("timeout_signal_grace_period")
    if timeout_signal_name is not None:
        warn_unsupported_ctest_option("timeout_signal_name")

    return canary.UnresolvedSpec(**kwargs)  # ty: ignore[missing-argument]


def env_mods(mods: list[dict[str, str]]) -> list[dict[str, str]]:
    my_mods: list[dict[str, str]] = []
    for em in mods:
        op, name, value = em["op"], em["name"], em["value"]
        entry: dict[str, str] = dict(name=name)
        match op:
            case "set" | "unset":
                entry.update({"value": value, "action": op})
            case "string_append":
                entry.update({"value": f"{os.getenv(name, '')}{value}", "action": "set"})
            case "string_prepend":
                entry.update({"value": f"{value}{os.getenv(name, '')}", "action": "set"})
            case "path_list_append":
                entry.update({"value": value, "action": "append-path", "sep": ":"})
            case "path_list_prepend":
                entry.update({"value": value, "action": "prepend-path", "sep": ":"})
            case "cmake_list_append":
                entry.update({"value": value, "action": "append-path", "sep": ";"})
            case "cmake_list_prepend":
                entry.update({"value": value, "action": "prepend-path", "sep": ";"})
        my_mods.append(entry)
    return my_mods


def setup_ctest(case: canary.TestCase):
    sh = canary.filesystem.which("sh")
    exec_dir = case.spec.attributes["execution_directory"]
    args = case.spec.attributes["command"]
    variables = resource_groups_vars(case)
    case.add_variables(**variables)
    with case.workspace.openfile("runtest.sh", "w") as fh:
        fh.write(f"#!{sh}\n")
        fh.write(f"cd {exec_dir}\n")
        for name, value in variables.items():
            fh.write(f"export {name}={value}\n")
        fh.write(shlex.join(args))
    canary.filesystem.set_executable(case.workspace.joinpath("runtest.sh"))


def resource_groups_vars(case: canary.TestCase) -> dict[str, str]:
    """Set the resource group variables as required by CTest

    canary does not have a notion of resource groups, like ctest does.  When a test checks out
    resources from a pool the resources are in a dictionary of the form

      {str: list[spec]}

    where a spec is:

      {"slots": N, "count": N}

    """
    variables: dict[str, str] = {}
    resource_groups = case.spec.attributes.get("resource_groups") or []
    if not resource_groups:
        return variables
    avail: dict[str, Any] = {}
    for type, items in case.resources.items():
        slots_per_id: dict[str, Any] = {}
        for item in items:
            slots_per_id[item["id"]] = slots_per_id.get(item["id"], 0) + item["slots"]
        instances = [{"id": key, "slots": val} for key, val in slots_per_id.items()]
        avail[type] = sorted(instances, key=lambda x: x["slots"])
    for i, group in enumerate(resource_groups):
        types = sorted(set([_["type"] for _ in group]))
        variables[f"CTEST_RESOURCE_GROUP_{i}"] = ",".join(types)
        specs: dict[str, list] = {}
        for item in group:
            type = item["type"]
            if type not in avail:
                continue
            spec = specs.setdefault(type, [])
            slots = item["slots"]
            for inst in avail[type]:
                if inst["slots"] >= slots:
                    spec.append(f"id:{inst['id']},slots:{inst['slots']}")
                    inst["slots"] = inst["slots"] - slots
                    break
            else:
                raise ValueError(f"Insufficient slots of {type} to fill CTest resource group")
        for type, spec in specs.items():
            key = f"CTEST_RESOURCE_GROUP_{i}_{type.upper()}"
            variables[key] = ";".join(spec)
    variables["CTEST_RESOURCE_GROUP_COUNT"] = str(len(resource_groups))
    return variables


def finish_ctest(case: "canary.TestCase") -> None:
    output = case.read_output()

    if case.status.name in ("TIMEOUT", "SKIPPED", "CANCELLED"):
        return

    if pass_regular_expression := case.spec.attributes.get("pass_regular_expression"):
        for regex in pass_regular_expression:
            if re.search(regex, output, re.MULTILINE):
                case.status.set("SUCCESS")
                break
        else:
            regex = ", ".join(pass_regular_expression)
            case.status.set("FAILED", f"Regular expressions {regex} not found in {case.stdout}")

    if skip_return_code := case.spec.attributes.get("skip_return_code"):
        if case.status.code == skip_return_code:
            case.status.set("SKIPPED", f"Return code={skip_return_code!r}")

    if skip_regular_expression := case.attributes.get("skip_regular_expression"):
        for regex in skip_regular_expression:
            if re.search(regex, output, re.MULTILINE):
                case.status.set("SKIPPED", f"Regular expression {regex!r} found in {case.stdout}")
                break

    if fail_regular_expression := case.spec.attributes.get("fail_regular_expression"):
        for regex in fail_regular_expression:
            if re.search(regex, output, re.MULTILINE):
                case.status.set("FAILED", f"Regular expression {regex!r} found in {case.stdout}")
                break

    # invert logic
    if case.spec.attributes.get("will_fail"):
        if case.status.name == "SUCCESS":
            case.status.set("FAILED", "Test case marked will_fail but succeeded")
        elif case.status.name not in ("SKIPPED",):
            case.status.set("SUCCESS")


def safeint(arg: str) -> None | int:
    try:
        return int(arg)
    except (ValueError, TypeError):
        return None


def parse_np(args: list[str]) -> int | None:
    iterargs = iter(args)
    while True:
        try:
            arg = next(iterargs)
        except StopIteration:
            break
        if re.search("^-(n|np|c)$", arg):
            if i := safeint(next(iterargs)):
                return i
        elif re.search("^--np$", arg):
            if i := safeint(next(iterargs)):
                return i
        elif match := re.search("^-(n|np|c)([0-9]+)$", arg):
            if i := int(match.group(2)):
                return i
        elif match := re.search("^--np=([0-9]+)$", arg):
            if i := int(match.group(1)):
                return i
    return None


def load(file: str) -> dict[str, Any]:
    """Use ctest --show-only"""
    tests: dict[str, Any] = {}
    logger.debug(f"Loading ctest tests from {file}")

    ctest = canary.filesystem.which("ctest")
    assert ctest is not None

    with canary.filesystem.working_dir(os.path.dirname(file)):
        project_binary_dir: str | None = find_project_binary_dir(os.path.dirname(file))
        project_source_dir: str | None = None
        if project_binary_dir is not None:
            project_source_dir = infer_project_source_dir(project_binary_dir)

        try:
            with open(".ctest-json-v1.json", "w") as fh:
                args = [ctest, "--show-only=json-v1"]
                if ctest_config := canary.config.getoption("canary_cmake_ctest_config"):
                    args.extend(["-C", ctest_config])
                p = subprocess.Popen(args, stdout=fh)
                p.wait()
            with open(".ctest-json-v1.json", "r") as fh:
                payload = json.load(fh)
        finally:
            canary.filesystem.force_remove(".ctest-json-v1.json")

        nodes = payload["backtraceGraph"]["nodes"]
        files = payload["backtraceGraph"]["files"]
        for test in payload["tests"]:
            if "command" not in test:
                # this test does not define a command
                continue
            t = tests.setdefault(test["name"], {})
            t["properties"] = test["properties"]
            t["command"] = test["command"]
            t["file"] = os.path.abspath(file)

            # Determine where this test is defined
            t["ctestfile"] = None
            if nodes and project_source_dir is not None and project_binary_dir is not None:
                node = nodes[test["backtrace"]]
                while True:
                    if "parent" not in node:
                        break
                    node = nodes[node["parent"]]
                f = os.path.abspath(files[node["file"]])
                if os.access(f, os.R_OK):
                    # With the CMakeList we can infer the CTest file if we can find the project
                    # source directory
                    reldir = os.path.relpath(os.path.dirname(f), project_source_dir)
                    f = os.path.join(project_binary_dir, reldir, "CTestTestfile.cmake")
                    if os.path.exists(f):
                        t["ctestfile"] = f
            if t["ctestfile"] is None or not os.path.exists(t["ctestfile"]):
                for prop in t["properties"]:
                    if prop["name"] == "WORKING_DIRECTORY":
                        working_directory = prop["value"]
                        f = os.path.join(working_directory, "CTestTestfile.cmake")
                        if os.path.exists(f):
                            # Assume that this test is defined in this file (which is not a guarantee)
                            t["ctestfile"] = os.path.abspath(f)
                            break
            if t["ctestfile"] is None or not os.path.exists(t["ctestfile"]):
                t["ctestfile"] = file

            assert os.path.exists(t["ctestfile"]), "CTestTestfile.cmake not found"

    return tests


def find_project_binary_dir(start: str) -> str | None:
    dirname = start
    while True:
        cmakecache = os.path.join(dirname, "CMakeCache.txt")
        if os.path.exists(cmakecache):
            return dirname
        dirname = os.path.dirname(dirname)
        if dirname == os.path.sep:
            break
    return None


def infer_project_source_dir(project_binary_dir: str) -> str | None:
    f = os.path.join(project_binary_dir, "CMakeCache.txt")
    cache = open(f, "r").read()
    if match := re.search(r"(?im)^\s*CMAKE_PROJECT_NAME.*=(.*)", cache):
        name = match.group(1)
        if match := re.search(r"(?im)^\s*%s_SOURCE_DIR.*=(.*)" % name, cache):
            return match.group(1)
    return None


def find_cmake():
    cmake = canary.filesystem.which("cmake")
    if cmake is None:
        return None
    out = subprocess.check_output([cmake, "--version"]).decode("utf-8")
    parts = [_.strip() for _ in out.split() if _.split()]
    if parts and parts[0:2] == ["cmake", "version"]:
        version_parts = tuple([int(_) for _ in parts[2].split(".")])
        if version_parts[:2] <= (3, 20):
            logger.warning("canary ctest integration requires cmake > 3.20")
            return None
        return cmake
    return None


def parse_resource_groups(resource_groups: list[dict[str, list]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for rg in resource_groups:
        group: list[dict[str, Any]] = []
        for requirement in rg["requirements"]:
            type, slots = requirement[".type"], requirement["slots"]
            group.append({"type": type, "slots": slots})
        groups.append(group)
    return groups


def parse_environment(environment: list[str]) -> dict[str, str]:
    """Convert the CTest ENVIRONMENT list[str] to dict[str, str]:

    ["name=value", ..., "name=value"] -> {"name": "value", ...}
    """
    env: dict[str, str] = {}
    for item in environment:
        key, value = item.split("=", 1)
        env[key] = value
    return env


def parse_environment_modification(environment_modification: list[str]) -> list[dict[str, str]]:
    """Convert the CTest ENVIRONMENT_MODIFICATION list[str] to list[dict]:

    ["name=op:value", ..., "name=op:value"] -> [{"name": "name", "op": "op", "value": "value", ...}]
    """
    envmod: list[dict[str, str]] = []
    for item in environment_modification:
        if match := re.search("([^=]+)=([a-z_]+):(.*)", item):
            name, op, value = match.group(1), match.group(2), match.group(3)
            envmod.append({"name": name, "op": op, "value": value})
    return envmod


def read_resource_specs(file: str) -> dict:
    with open(file) as fh:
        data = json.load(fh)
    resource_specs = validate_resource_specs(data)
    return resource_specs


def validate_resource_specs(resource_specs: dict) -> dict:
    resource_spec_schema = schema.Schema(
        {
            "local": {
                str: [
                    {
                        "id": schema.Use(str),
                        schema.Optional("slots", default=1): schema.Or(int, float),  # type: ignore
                    }
                ]
            }
        }
    )
    return resource_spec_schema.validate(resource_specs)
