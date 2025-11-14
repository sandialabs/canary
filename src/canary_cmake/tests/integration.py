# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import importlib.resources
import os
import subprocess
import sys

import pytest

import _canary.config
import _canary.util.executable as ex
import _canary.util.filesystem as fs

f1 = fs.which("gcc") or os.getenv("CC")
f2 = fs.which("cmake")
nvf = str(importlib.resources.files("_canary").joinpath("../canary/tools/Canary.cmake"))
good = f1 is not None and f2 is not None and os.path.exists(nvf)


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.Config()
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)


@pytest.mark.skipif(not good, reason="gcc and/or cmake not on PATH")
def test_cmake_integration(tmpdir):
    from _canary.util.testing import CanaryCommand

    workdir = tmpdir.strpath
    with fs.working_dir(workdir, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("baz.pyt", "w") as fh:
            fh.write("def test():\n    return 0\ntest()\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.18...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("enable_testing()\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_test(NAME spam COMMAND foo)\n")
            fh.write("add_canary_test(NAME foo COMMAND foo)\n")
            fh.write("add_canary_test(NAME baz SCRIPT baz.pyt)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake("..", fail_on_error=False)
            if cmake.returncode != 0:
                print("WARNING: cmake failed!")
                return
            assert os.path.exists("foo.pyt")
            assert os.path.exists("baz.pyt")
            make = ex.Executable("make")
            make()
            print(os.listdir("."))
            run = CanaryCommand("run")
            run.add_default_args("-r", "cpus:6", "-r", "gpus:0")
            run("-w", "--recurse-ctest", ".", debug=True)
            dirs = sorted(os.listdir("TestResults"))
            assert len(dirs) == 4
            assert set(dirs) == {"VIEW.TAG", "baz", "foo", "spam"}


f3 = fs.which("mpirun")
good = good and f3 is not None


@pytest.mark.skipif(not good, reason="gcc, cmake, and/or mpirun not found on PATH")
def test_cmake_integration_parallel(tmpdir):
    assert f3 is not None
    mpi_home = os.path.dirname(os.path.dirname(f3))
    from _canary.util.testing import CanaryCommand

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("find_package(MPI)\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_parallel_canary_test(NAME foo COMMAND foo NPROC 4)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake(f"-DCMAKE_PREFIX_PATH={mpi_home}", "..", fail_on_error=False)
            if cmake.returncode != 0:
                print("WARNING: cmake failed!")
                return
            assert os.path.exists("foo.pyt")
            make = ex.Executable("make")
            make()
            run = CanaryCommand("run")
            run.add_default_args("-r", "cpus:6", "-r", "gpus:0")
            cp = run("-w", ".", debug=True, check=False)
            if cp.returncode != 0:
                files = glob.glob("TestResults/**/canary-*.txt", recursive=True)
                for file in files:
                    print(f"{file}:")
                    print(open(file).read())
                assert 0, "test failed"
            assert len(os.listdir("TestResults")) == 2


f3 = fs.which("mpirun")
good = good and f3 is not None


@pytest.mark.skipif(not good, reason="gcc, cmake, and/or mpirun not found on PATH")
def test_cmake_integration_parallel_override(tmpdir):
    assert f3 is not None
    mpi_home = os.path.dirname(os.path.dirname(f3))
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("find_package(MPI)\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_parallel_canary_test(NAME foo COMMAND foo NPROC 4)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake(
                f"-DCMAKE_PREFIX_PATH={mpi_home}",
                "-DMPIEXEC_EXECUTABLE_OVERRIDE=my-mpirun",
                "-DMPIEXEC_NUMPROC_FLAG_OVERRIDE=-x",
                "..",
                fail_on_error=False,
            )
            if cmake.returncode != 0:
                print("WARNING: cmake failed!")
                return
            with open("foo.pyt") as fh:
                lines = fh.read()
                assert 'mpi = canary.Executable("my-mpirun")' in lines
                assert 'args.extend(["-x", str(self.parameters.cpus)])' in lines


@pytest.mark.skipif(not good, reason="gcc and/or cmake not on PATH")
def test_cmake_integration_build_config(tmpdir):
    workdir = tmpdir.strpath
    with fs.working_dir(workdir, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.18...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("write_canary_config()\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake("..", fail_on_error=False)
            if cmake.returncode != 0:
                print("WARNING: cmake failed!")
                return
            make = ex.Executable("make")
            make()
            p = subprocess.Popen(
                [sys.executable, "-m", "canary", "-d", "config", "show"], stdout=subprocess.PIPE
            )
            p.wait()
            #            out = p.communicate()[0].decode("utf-8")
            #            print(out)
            assert p.returncode == 0
