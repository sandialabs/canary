import os

import pytest

from _nvtest.plugins.nvtest_ctest.generator import CTestTestFile
from _nvtest.runners import TestCaseRunner as xTestCaseRunner
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import set_executable
from _nvtest.util.filesystem import touchp
from _nvtest.util.filesystem import which
from _nvtest.util.filesystem import working_dir


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touchp("mpiexec")
        touchp("script.sh")
        touchp("some-exe")
        set_executable("script.sh")
        set_executable("some-exe")
        set_executable("mpiexec")
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(test1 "script.sh" "some-exe")
set_tests_properties(test1 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;SPAM=BAZ" LABELS "foo;baz" PROCESSORS "5" RESOURCE_GROUPS "5,gpus:1" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
add_test(test2 "mpiexec" "-n" "4" "some-exe")
set_tests_properties(test2 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;EGGS=SPAM" LABELS "foo;spam" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        cases = file.lock()
        assert len(cases) == 2

        case = cases[0]
        assert case.cpus == 5
        assert case.gpus == 5
        assert "foo" in case.keywords
        assert "baz" in case.keywords
        assert case.launcher is None
        assert case.command() == ["script.sh", "some-exe"]
        assert case.variables["CTEST_NUM_RANKS"] == "5"
        assert case.variables["SPAM"] == "BAZ"

        case = cases[1]
        assert case.launcher.endswith("mpiexec")
        assert case.command() == ["mpiexec", "-n", "4", "some-exe"]
        assert case.cpus == 4
        assert "foo" in case.keywords
        assert "spam" in case.keywords
        assert case.variables["CTEST_NUM_RANKS"] == "5"
        assert case.variables["EGGS"] == "SPAM"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_1(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("enable_testing()\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_test(NAME foo COMMAND foo)\n")
            fh.write('set_tests_properties(foo PROPERTIES LABELS "foo;baz" PROCESSORS 4)\n')
        with working_dir("build", create=True):
            cmake = Executable("cmake")
            cmake("..")
            file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
            cases = file.lock()
            assert len(cases) == 1
            case = cases[0]
            assert case.cpus == 4
            assert "foo" in case.keywords
            assert "baz" in case.keywords


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_fail_regular_expression(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(test1 "echo" "This test should fail")
set_tests_properties(test1 PROPERTIES  FAIL_REGULAR_EXPRESSION "^This test should fail$")
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        [case] = file.lock()
        runner = xTestCaseRunner()
        mkdirp("./foo")
        case.setup(work_tree=f"{os.getcwd()}/foo")
        runner.run(case)
        assert case.returncode == 0
        assert case.status == "failed"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_skip_regular_expression(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("script.sh", "w") as fh:
            fh.write("#!/usr/bin/env bash\necho 'This test should be skipped'\nexit 1")
        set_executable("script.sh")
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(test1 "./script.sh")
set_tests_properties(test1 PROPERTIES  SKIP_REGULAR_EXPRESSION "^This test should be skipped$")
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        [case] = file.lock()
        runner = xTestCaseRunner()
        mkdirp("./foo")
        case.setup(work_tree=f"{os.getcwd()}/foo")
        runner.run(case)


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_pass_regular_expression(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("script.sh", "w") as fh:
            fh.write("#!/usr/bin/env bash\necho 'This test should pass'\nexit 1")
        set_executable("script.sh")
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(test1 "./script.sh")
set_tests_properties(test1 PROPERTIES  PASS_REGULAR_EXPRESSION "^This test should pass$")
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        [case] = file.lock()
        runner = xTestCaseRunner()
        mkdirp("./foo")
        case.setup(work_tree=f"{os.getcwd()}/foo")
        print(case.cache_directory)
        print(os.listdir(case.cache_directory))
        print(case.working_directory)
        print(os.listdir(case.working_directory))
        runner.run(case)
        assert case.status == "success"
        assert case.returncode == 1


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_fixtures(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(setup_foo "ls" "/")
add_test(setup_bar "ls" "/")
add_test(cleanup_foo "ls" "/")
add_test(cleanup_bar "ls" "/")
add_test(test_foo "ls" "/")
add_test(test_bar "ls" "/")
add_test(test_both "ls" "/")
add_test(oddball "ls" "/")
set_tests_properties(setup_foo PROPERTIES FIXTURES_REQUIRED Oddball)
set_tests_properties(test_foo PROPERTIES FIXTURES_REQUIRED Foo)
set_tests_properties(test_bar PROPERTIES FIXTURES_REQUIRED Bar)
set_tests_properties(test_both PROPERTIES FIXTURES_REQUIRED "Foo;Bar")
set_tests_properties(oddball PROPERTIES FIXTURES_SETUP Oddball)
set_tests_properties(setup_foo PROPERTIES FIXTURES_SETUP Foo)
set_tests_properties(setup_bar PROPERTIES FIXTURES_SETUP Bar)
set_tests_properties(cleanup_foo PROPERTIES FIXTURES_CLEANUP Foo)
set_tests_properties(cleanup_bar PROPERTIES FIXTURES_CLEANUP Bar)
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        cases = file.lock()
        assert len(cases) == 8
        case_map = {case.name: case for case in cases}
        assert len(case_map["oddball"].dependencies) == 0
        assert len(case_map["setup_foo"].dependencies) == 0
        assert len(case_map["setup_bar"].dependencies) == 0
        assert case_map["cleanup_bar"].dependencies == [
            case_map["test_bar"],
            case_map["test_both"],
        ]
        assert case_map["cleanup_foo"].dependencies == [
            case_map["test_foo"],
            case_map["test_both"],
        ]
        assert case_map["test_bar"].dependencies == [case_map["setup_bar"]]
        assert case_map["test_foo"].dependencies == [case_map["setup_foo"]]
        assert case_map["test_both"].dependencies == [case_map["setup_foo"], case_map["setup_bar"]]
