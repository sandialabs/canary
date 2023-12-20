import glob
import json
import os
from typing import Any
from typing import Optional

import nvtest
from _nvtest.test import TestCase
from _nvtest.util import tty
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import which
from _nvtest.util.filesystem import working_dir


# @nvtest.plugin.register(scope="main", stage="setup")
def llvm_coverage_parser(parser: nvtest.Parser) -> None:
    parser.add_plugin_argument(
        "--coverage",
        action="store_true",
        default=False,
        help="Perform test case coverage",
    )
    parser.add_plugin_argument(
        "--cov-prefix", help="Code prefix to strip from coverage maps"
    )


@nvtest.plugin.register(scope="test", stage="setup")
def llvm_coverage_setup(case: TestCase) -> None:
    if not nvtest.config.get("option:coverage"):
        return
    elif not hasattr(case, "program"):
        tty.warn(f"{case} does not define a 'program' attribute, coverage skipped")
        return
    if case.masked:
        return
    if os.path.exists(case.exec_dir):
        with working_dir(case.exec_dir):
            files = glob.glob(f"{case.family}-*.profraw")
            for file in files:
                force_remove(file)
    case.variables["LLVM_PROFILE_FILE"] = f"{case.family}-%p.profraw"


@nvtest.plugin.register(scope="test", stage="teardown")
def llvm_coverage_teardown(case: TestCase, **kwargs: Any) -> None:
    if not nvtest.config.get("option:coverage"):
        return
    elif not hasattr(case, "program"):
        tty.warn(f"{case} does not define a 'program' attribute, coverage skipped")
    export_profile_data(case)


def export_profile_data(case: TestCase) -> None:
    f = _merge_profile_data(case)
    if f is None:
        return
    _export_profile_data(case, f)


def _merge_profile_data(case: TestCase) -> Optional[str]:
    path = which("llvm-profdata")
    if path is None and nvtest.config.get("build:compiler"):
        cc = nvtest.config.get("build:compiler:paths:cxx")
        path = which("llvm-profdata", path=os.path.dirname(cc))
    if path is None:
        tty.warn("Unable to find llvm-profdata.  Profile data cannot be exported")
        return
    files = glob.glob(f"{case.family}-*.profraw")
    if not files:
        tty.warn("Profile files not found.  Profile data cannot be exported")
        return
    tty.info("Merging profile data")
    dst = f"{case.family}.merged"
    args = ["merge", "-sparse"] + files + ["-o", dst]
    prog = Executable(path)
    prog(*args, fail_on_error=False)
    if prog.returncode != 0:
        tty.error(f"Failed to merge profile data for {case.name}")
    tty.info("Done merging profile data")
    return dst if prog.returncode == 0 else None


def _export_profile_data(case: TestCase, file: str) -> None:
    tty.info("Exporting profile data")
    path = which("llvm-cov")
    if path is None and nvtest.config.get("build"):
        cc = nvtest.config.get("build:compiler:paths:cxx")
        path = which("llvm-cov", path=os.path.dirname(cc))
    if path is None:
        tty.warn("Unable to find llvm-cov.  Profile data cannot be exported")
        return
    # FIXME
    args = ["export", case.program, f"-instr-profile={file}", "--summary-only"]
    prog = Executable(path)
    output = prog(*args, output=str)
    data = json.loads(output)
    _filter_profile_data(data)
    with open(f"{case.family}-profile.json", "w") as fh:
        json.dump(data, fh, indent=2)
    tty.info("Done exporting profile data")


def _filter_profile_data(fd: dict) -> None:
    files = fd["data"][0].pop("files")
    filtered = fd["data"][0].setdefault("files", [])
    prefix = nvtest.config.get("option:cov_prefix")
    for file in files:
        filename = file["filename"]
        if not filename.startswith(prefix):
            continue
        if not file["summary"]["lines"]["covered"]:
            continue
        path = filename.replace(prefix + os.path.sep, "")
        file["filename"] = path
        filtered.append(file)
    return
