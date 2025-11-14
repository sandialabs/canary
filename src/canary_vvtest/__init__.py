# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
import sys
import typing

import canary

from .generator import VVTTestGenerator

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_testcase_generator(root: str, path: str | None) -> canary.AbstractTestGenerator | None:
    if VVTTestGenerator.matches(root if path is None else os.path.join(root, path)):
        return VVTTestGenerator(root, path=path)
    return None


@canary.hookimpl
def canary_testcase_modify(case: "canary.TestCase") -> None:
    if case.file_path.endswith(".vvt"):
        case.ofile = "execute.log"
        case.efile = "<none>"  # causes stderr to be merged into stdout


@canary.hookimpl
def canary_testcase_setup(case: "canary.TestCase") -> None:
    if case.file_path.endswith(".vvt"):
        with canary.filesystem.working_dir(case.working_directory):
            write_vvtest_util(case)


class RerunAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        keywords = getattr(namespace, "keyword_exprs", None) or []
        keywords.append(":all:")
        namespace.keyword_exprs = list(keywords)
        setattr(namespace, self.dest, True)


class AnalyzeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        script_args = getattr(namespace, "script_args", None) or []
        script_args.append("--execute-analysis-sections")
        setattr(namespace, "script_args", list(script_args))
        opts = getattr(namespace, "canary_vvtest", None) or {}
        opts[self.dest] = True
        setattr(namespace, "canary_vvtest", opts)
        setattr(namespace, "dont_restage", True)


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


def write_vvtest_util(case: "canary.TestCase", stage: str = "run") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    attrs = get_vvtest_attrs(case)
    file = os.path.abspath("./vvtest_util.py")
    if os.path.dirname(file) != case.working_directory:
        raise ValueError("Incorrect directory for writing vvtest_util")
    with open(file, "w") as fh:
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
def get_vvtest_attrs(case: "canary.TestCase") -> dict:
    attrs = {}
    compiler_spec = None
    if vendor := canary.config.get("build:compiler:vendor"):
        version = canary.config.get("build:compiler:version")
        compiler_spec = f"{vendor}@{version}"
    attrs["CASEID"] = case.id
    attrs["NAME"] = case.family
    attrs["TESTID"] = case.fullname
    attrs["PLATFORM"] = sys.platform.lower()
    attrs["COMPILER"] = compiler_spec or "UNKNOWN@UNKNOWN"
    attrs["TESTROOT"] = case.session
    attrs["VVTESTSRC"] = ""
    attrs["PROJECT"] = ""
    attrs["OPTIONS"] = canary.config.getoption("on_options") or []
    attrs["OPTIONS_OFF"] = canary.config.getoption("off_options") or []
    attrs["SRCDIR"] = case.file_dir
    attrs["TIMEOUT"] = case.timeout
    attrs["KEYWORDS"] = case.keywords
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
    # to the command if canary_testcase_modify below
    analyze_check = "'--execute-analysis-sections' in sys.argv[1:]"
    attrs["opt_analyze"] = attrs["is_analysis_only"] = analyze_check

    attrs["is_analyze"] = isinstance(case, canary.TestMultiCase)
    attrs["is_baseline"] = canary.config.getoption("command") == "rebaseline"
    attrs["PARAM_DICT"] = case.parameters or {}
    for key, val in case.parameters.items():
        attrs[key] = val
    if isinstance(case, canary.TestMultiCase):
        for paramset in case.paramsets:
            key = "_".join(paramset.keys)
            table = attrs.setdefault(f"PARAM_{key}", [])
            for row in paramset.values:
                if len(paramset.keys) == 1:
                    table.append(row[0])
                else:
                    table.append(list(row))

    # DEPDIRS and DEPDIRMAP should always exist.
    attrs["DEPDIRS"] = [dep.working_directory for dep in getattr(case, "dependencies", [])]
    attrs["DEPDIRMAP"] = {}  # FIXME

    attrs["exec_dir"] = case.working_directory
    attrs["exec_root"] = case.session
    attrs["exec_path"] = case.path
    attrs["file_root"] = case.file_root
    attrs["file_dir"] = case.file_dir
    attrs["file_path"] = case.file_path

    attrs["RESOURCE_np"] = case.cpus
    attrs["RESOURCE_IDS_np"] = [int(_) for _ in case.cpu_ids]
    attrs["RESOURCE_ndevice"] = case.gpus
    attrs["RESOURCE_IDS_ndevice"] = [int(_) for _ in case.gpu_ids]

    return attrs
