import glob
import importlib.resources
import os
import subprocess
import sys

import pytest

import _nvtest.util.executable as ex
import _nvtest.util.filesystem as fs

f1 = fs.which("gcc") or os.getenv("CC")
f2 = fs.which("cmake")
nvf = str(importlib.resources.files("_nvtest").joinpath("../nvtest/tools/NVTest.cmake"))
good = f1 is not None and f2 is not None and os.path.exists(nvf)


@pytest.mark.skipif(not good, reason="gcc and/or cmake not on PATH")
def test_cmake_integration(tmpdir):
    from _nvtest.main import NVTestCommand

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
            fh.write("add_nvtest(NAME foo COMMAND foo)\n")
            fh.write("add_nvtest(NAME baz SCRIPT baz.pyt)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake("..")
            assert os.path.exists("foo.pyt")
            assert os.path.exists("baz.pyt")
            make = ex.Executable("make")
            make()
            print(os.listdir("."))
            run = NVTestCommand("run", debug=True)
            run("-w", ".")
            dirs = sorted(os.listdir("TestResults"))
            dirs.remove(".nvtest")
            assert len(dirs) == 3
            assert dirs == ["baz", "foo", "spam"]


f3 = fs.which("mpirun")
good = good and f3 is not None


@pytest.mark.skipif(not good, reason="gcc, cmake, and/or mpirun not found on PATH")
def test_cmake_integration_parallel(tmpdir):
    mpi_home = os.path.dirname(os.path.dirname(f3))
    from _nvtest.main import NVTestCommand

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("find_package(MPI)\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_parallel_nvtest(NAME foo COMMAND foo NPROC 4)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake(f"-DCMAKE_PREFIX_PATH={mpi_home}", "..")
            assert os.path.exists("foo.pyt")
            make = ex.Executable("make")
            make()
            run = NVTestCommand("run", debug=True)
            run("-w", ".", fail_on_error=False)
            if run.returncode != 0:
                files = glob.glob("TestResults/**/nvtest-out.txt", recursive=True)
                for file in files:
                    print(open(file).read())
                assert 0, "test failed"
            assert len(os.listdir("TestResults")) == 2


f3 = fs.which("mpirun")
good = good and f3 is not None


@pytest.mark.skipif(not good, reason="gcc, cmake, and/or mpirun not found on PATH")
def test_cmake_integration_parallel_override(tmpdir):
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
            fh.write("add_parallel_nvtest(NAME foo COMMAND foo NPROC 4)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake(
                f"-DCMAKE_PREFIX_PATH={mpi_home}",
                "-DMPIEXEC_EXECUTABLE_OVERRIDE=my-mpirun",
                "-DMPIEXEC_NUMPROC_FLAG_OVERRIDE=-x",
                "..",
            )
            with open("foo.pyt") as fh:
                lines = fh.read()
                assert 'mpi = nvtest.Executable("my-mpirun")' in lines
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
            fh.write("write_nvtest_config()\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake("..")
            make = ex.Executable("make")
            make()
            p = subprocess.Popen(
                [sys.executable, "-m", "nvtest", "-d", "config", "show"], stdout=subprocess.PIPE
            )
            p.wait()
            #            out = p.communicate()[0].decode("utf-8")
            #            print(out)
            assert p.returncode == 0
