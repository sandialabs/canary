# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import json
import re
import sys
import typing

import canary

from .vvt import VVTestAdapter
from .vvt import VVTestLoader
from .vvt import VVTestLockEmitter
from .vvt import VVTestModel

logger = canary.get_logger(__name__)


class VVTestSpecGenerator(canary.AbstractSpecGenerator):
    file_patterns: typing.ClassVar[tuple[str, ...]] = ("*.vvt",)

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.model = VVTestModel(root=self.root, path=self.path)  # whatever context needed
        self.adapter = VVTestAdapter(self.model)
        calls = VVTestLoader(file=self.file).parse()
        self.adapter.apply(calls)

    def lock(self, on_options=None):
        return VVTestLockEmitter().lock(self.model, on_options=on_options)

    def describe(self, on_options: list[str] | None = None) -> str:
        import io
        import os

        from _canary.generate import resolve
        from _canary.util import graph
        from _canary.util.field import Field
        from _canary.util.string import pluralize

        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Keywords: {', '.join(self.model.get_keywords(on_options=on_options))}\n")
        options = self.model.option_expressions()
        if options:
            file.write(f"Recognized options: {', '.join(options)}\n")

        # Print raw (unsubstituted) source specs if present
        if hasattr(self.model, "sources") and isinstance(getattr(self.model, "sources"), Field):
            src_field = getattr(self.model, "sources")
            if src_field.items:
                file.write("Source files:\n")
                grouped: dict[str, list[tuple[str, str | None]]] = {}
                for c in src_field.items:
                    s = c.value
                    grouped.setdefault(s.action, []).append((s.src, s.dst))
                for action, files in grouped.items():
                    file.write(f"  {action.title()}:\n")
                    for src, dst in files:
                        file.write(f"    {src}")
                        if dst and dst != os.path.basename(src):
                            file.write(f" -> {dst}")
                        file.write("\n")

        try:
            specs = self.lock(on_options=on_options)
            resolved = resolve(specs)
            n = len(specs)
            opts = ", ".join(on_options or [])
            file.write(f"{n} test {pluralize('spec', n)} using on_options={opts}:\n")
            try:
                graph.print(resolved, file=file)
            except Exception:  # nosec B110
                pass
        except Exception:
            logger.warning("Unable to generate dependency graph")
        return file.getvalue()

    def info(self) -> dict[str, typing.Any]:
        info: dict[str, typing.Any] = super().info()
        info["keywords"] = self.model.get_keywords()
        info["options"] = self.model.option_expressions()
        return info


@canary.hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(VVTestSpecGenerator)


@canary.hookimpl
def canary_generate_modifyitems(generator: "canary.Generator") -> None:
    for spec in generator.specs:
        if spec.file_path.suffix == ".vvt":
            spec.stdout = "execute.log"
            spec.stderr = None
            set_vvtest_exec_path(spec)
            if "np" in spec.parameters:
                spec.meta_parameters["cpus"] = spec.parameters["np"]
            if "ndevice" in spec.parameters:
                spec.meta_parameters["gpus"] = spec.parameters["ndevice"]
            if "nnode" in spec.parameters:
                spec.meta_parameters["nodes"] = spec.parameters["nnode"]


@canary.hookimpl
def canary_cdash_name(case: canary.Job) -> str | None:
    if not case.spec.file_path.suffix == ".vvt":
        return None
    elif not case.spec.parameters:
        return case.spec.family
    _, _, s = case.spec.exec_path.name.partition(".")
    pattern = re.compile(r"([^.=]+)=.*?(?=\. [^.=]+=|$)", re.VERBOSE)
    s_params = ",".join([m.group() for m in pattern.finditer(s)])
    return f"{case.spec.family}[{s_params}]"


@canary.hookimpl
def canary_runteststart(case: "canary.Job") -> None:
    if case.spec.file_path.suffix == ".vvt":
        with canary.filesystem.working_dir(case.workspace.dir):
            write_vvtest_util(case)


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "-R",
        action=RerunAction,
        nargs=0,
        command="run",
        group="vvtest options",
        dest="vvtest_runall",
        help="Rerun tests. Normally tests are not run if they previously completed.",
    )
    parser.add_argument(
        "-a",
        "--analyze",
        action=AnalyzeAction,
        nargs=0,
        command="run",
        group="vvtest options",
        dest="analyze",
        help="Only run the analysis sections of each test. Note that a test must be written to "
        "support this option (using the vvtest_util.is_analysis_only flag) otherwise the whole "
        "test is run.",
    )


def set_vvtest_exec_path(spec: "canary.JobSpec") -> None:
    """Set the execution path of the job

    In the vvtest generator we call ``scalar.cast`` on each value.  That operation puts a
    ``string`` attribute on each value that is the string parameter given in the vvtest file.  this
    parameter is used for constructing execution path
    """
    getstr = lambda v: getattr(v, "string", str(v))
    parts = [f"{p}={getstr(spec.parameters[p])}" for p in sorted(spec.parameters.keys())]
    name = spec.family
    if parts:
        name = "%s.%s" % (name, ".".join(parts))
    spec.exec_path = spec.file_path.parent / name
    spec.view_path = spec.file_path.parent / name


class RerunAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, "only", "all")


class AnalyzeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        script_args = getattr(namespace, "script_args", None) or []
        script_args.append("--execute-analysis-sections")
        setattr(namespace, "script_args", list(script_args))
        opts = getattr(namespace, "canary_vvtest", None) or {}
        opts[self.dest] = True
        setattr(namespace, "canary_vvtest", opts)


def write_vvtest_util(job: "canary.Job", stage: str = "run") -> None:
    if not job.spec.file_path.suffix == ".vvt":
        return
    attrs = get_vvtest_attrs(job)
    with job.workspace.openfile("vvtest_util.py", "w") as fh:
        fh.write("import os\n")
        fh.write("import sys\n")
        for key, value in attrs.items():
            if isinstance(value, bool):
                fh.write(f"{key} = {value!r}\n")
            elif value is None:
                fh.write(f"{key} = None\n")
            elif isinstance(value, str) and "in sys.argv" in value:
                fh.write(f"{key} = {value}\n")
            else:
                fh.write(f"{key} = {json.dumps(value, indent=4)}\n")


@typing.no_type_check
def get_vvtest_attrs(job: "canary.Job") -> dict:
    attrs = {}
    compiler_spec = None
    if vendor := canary.config.get("cmake:compiler:vendor"):
        version = canary.config.get("cmake:compiler:version")
        compiler_spec = f"{vendor}@{version}"
    attrs["JOBID"] = job.spec.id
    attrs["CASEID"] = job.spec.id
    attrs["NAME"] = job.spec.family
    attrs["TESTID"] = job.spec.fullname
    attrs["PLATFORM"] = sys.platform.lower()
    attrs["COMPILER"] = compiler_spec or "UNKNOWN@UNKNOWN"
    attrs["TESTROOT"] = str(job.workspace.root)
    attrs["VVTESTSRC"] = ""
    attrs["PROJECT"] = ""
    attrs["OPTIONS"] = canary.config.getoption("on_options") or []
    attrs["OPTIONS_OFF"] = canary.config.getoption("off_options") or []
    attrs["SRCDIR"] = str(job.spec.file.parent)
    attrs["TIMEOUT"] = job.spec.timeout
    attrs["KEYWORDS"] = job.spec.keywords
    attrs["diff_exit_status"] = 64
    attrs["skip_exit_status"] = 63

    # tjfulle: the vvtest_util.opt_analyze and vvtest_util.is_analysis_only attributes seem to
    # always be the same to me.  so far as I can tell, if you set -a/--analyze on the command line
    # the runtime config 'analyze' is set to True.  When vvtest writes out vvtest_util.py it writes
    #   - ``vvtest_util.is_analysis_only = rtconfig.getAttr("analyze")``; and
    #   - ``vvtest_util.opt_analyze = '--execute-analysis-sections' in sys.argv[1:].
    # ``--execute-analysis-sections`` is a appended to a test script's command line if
    # rtconfig.getAttr("analyze") is True.  Thus, it seems that there is no differenece between
    # ``opt_analyze`` and ``is_analysis_only``.  In canary, --execute-analysis-sections is added
    # in the AnalyzeAction class below
    analyze_check = "'--execute-analysis-sections' in sys.argv[1:]"
    attrs["opt_analyze"] = attrs["is_analysis_only"] = analyze_check

    attrs["is_analyze"] = "multicase" in job.spec.attributes
    attrs["is_baseline"] = canary.config.getoption("command") == "rebaseline"
    attrs["PARAM_DICT"] = job.spec.parameters or {}
    for key, val in job.spec.parameters.items():
        attrs[key] = val
    if attrs["is_analyze"]:
        for paramset in job.spec.attributes["paramsets"]:
            key = "_".join(paramset["keys"])
            table = attrs.setdefault(f"PARAM_{key}", [])
            for row in paramset["values"]:
                if len(paramset["keys"]) == 1:
                    table.append(row[0])
                else:
                    table.append(list(row))

    # DEPDIRS and DEPDIRMAP should always exist.
    attrs["DEPDIRS"] = [str(dep.job.workspace.dir) for dep in job.dependencies]
    attrs["DEPDIRMAP"] = {}  # FIXME

    attrs["exec_dir"] = str(job.workspace.dir)
    attrs["exec_root"] = str(job.workspace.root)
    attrs["exec_path"] = str(job.workspace.path)
    attrs["file_root"] = str(job.spec.file_root)
    attrs["file_dir"] = str(job.spec.file.parent)
    attrs["file_path"] = str(job.spec.file_path)

    attrs["RESOURCE_np"] = job.cpus
    attrs["RESOURCE_IDS_np"] = [int(_) for _ in job.cpu_ids]
    attrs["RESOURCE_ndevice"] = job.gpus
    attrs["RESOURCE_IDS_ndevice"] = [int(_) for _ in job.gpu_ids]

    return attrs
