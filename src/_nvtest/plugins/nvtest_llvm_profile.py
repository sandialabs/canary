import os
from typing import Optional

import nvtest


@nvtest.plugin.register("bootstrap-llvm-profile", scope="session", stage="bootstrap")
def bootstrap_llvm_profile(session: nvtest.Session) -> None:
    session.parser.add_plugin_argument(
        "--llvm-profile",
        action="store_true",
        default=False,
        help="Emit profile data for a test.  "
        "Each test must define the `program` attribute which is the path "
        "to the program to be profiled.  The 'llvm-profdata' and 'llvm-cov' "
        "executables must be found on your PATH [default: %(default)s]",
    )


@nvtest.plugin.register("setup-llvm-profile", scope="test", stage="setup")
def setup_llvm_profile(session: nvtest.Session, test: nvtest.TestCase, **kwds) -> None:
    llvm_profile = getattr(session.option, "llvm_profile", False)
    if llvm_profile:
        test.add_default_env("LLVM_PROFILE_FILE", "llvm-profile.raw")


@nvtest.plugin.register("teardown-llvm-profile", scope="test", stage="teardown")
def teardown_llvm_profile(session: nvtest.Session, test: nvtest.TestCase, **kwds):
    llvm_profile = getattr(session.option, "llvm_profile", False)
    if not llvm_profile:
        return
    program = getattr(test, "program", None)
    if program is None:
        nvtest.tty.warn(
            f"teardown_llvm_profile: {test} does not define 'program', "
            "profile data will not be merged"
        )
        return
    elif not os.path.exists(program):
        nvtest.tty.error(f"teardown_llvm_profile: {program}: executable not found")
        return
    f = _merge_profile_data(test)
    if f is not None:
        _export_profile_data(program, f)


def _merge_profile_data(test: nvtest.TestCase) -> Optional[str]:
    path = nvtest.which("llvm-profdata")
    # if path is None:
    #     cc = nevada.config.get("alegranevada:compiler:paths:cxx")
    #     path = nvtest.which("llvm-profdata", path=os.path.dirname(cc))
    if path is None:
        nvtest.tty.warn(
            "Unable to find llvm-profdata.  Profile data cannot be exported"
        )
        return None
    if "LLVM_PROFILE_FILE" in test.variables:
        file = test.variables["LLVM_PROFILE_FILE"]
    elif "LLVM_PROFILE_FILE" in os.environ:
        file = os.environ["LLVM_PROFILE_FILE"]
    else:
        nvtest.tty.warn(
            "LLVM_PROFILE_FILE not defined.  Profile data cannot be exported"
        )
        return None
    nvtest.tty.info("Merging profile data")
    dst = f"{os.path.splitext(os.path.basename(file))[0]}.merged"
    args = ["merge", "-sparse", file, "-o", dst]
    prog = nvtest.Executable(path)
    prog(*args, fail_on_error=False)
    nvtest.tty.info("Done merging profile data")
    return dst if prog.returncode == 0 else None


def _export_profile_data(program: str, file: str) -> None:
    nvtest.tty.info("Exporting profile data")
    path = nvtest.which("llvm-cov")
    # if path is None:
    #    cc = nevada.config.get("alegranevada:compiler:paths:cxx")
    #    path = nvtest.which("llvm-cov", path=os.path.dirname(cc))
    if path is None:
        nvtest.tty.warn("Unable to find llvm-cov.  Profile data cannot be exported")
        return
    args = ["export", program, f"-instr-profile={file}", "--summary-only"]
    prog = nvtest.Executable(path)
    with open("llvm-profile.json", "w") as fh:
        prog(*args, output=fh)
    nvtest.tty.info("Done exporting profile data")
