# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import multiprocessing
import os
from pathlib import Path

import pytest

import _canary.testcase as tc
import canary
from _canary.resource_pool import ResourcePool
from _canary.testexec import ExecutionSpace
from _canary.util.executable import Executable
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import set_executable
from _canary.util.filesystem import touchp
from _canary.util.filesystem import which
from _canary.util.filesystem import working_dir
from canary_cmake.ctest import CTestTestGenerator
from canary_cmake.ctest import setup_ctest


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, case):
        queue = multiprocessing.Queue()
        try:
            canary.config.pluginmanager.hook.canary_testcase_setup(case=case)
            canary.config.pluginmanager.hook.canary_testcase_run(case=case, queue=queue)
        finally:
            canary.config.pluginmanager.hook.canary_testcase_finish(case=case)


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
        mkdirp("CMakeFiles")
        with open("CMakeCache.txt", "w") as fh:
            fh.write(f"PROJECT_SOURCE_DIR:INTERNAL={os.getcwd()}")
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        specs = file.lock()
        assert len(specs) == 2

        spec = specs[0]
        assert spec.rparameters["cpus"] == 5
        assert spec.rparameters["gpus"] == 5
        assert "foo" in spec.keywords
        assert "baz" in spec.keywords
        command = spec.attributes["command"]
        command[0] = os.path.basename(command[0])
        assert command == ["script.sh", "some-exe"]
        assert spec.environment["CTEST_NUM_RANKS"] == "5"
        assert spec.environment["SPAM"] == "BAZ"

        spec = specs[1]
        command = spec.attributes["command"]
        command[0] = os.path.basename(command[0])
        assert command == ["mpiexec", "-n", "4", "some-exe"]
        assert spec.rparameters["cpus"] == 4
        assert "foo" in spec.keywords
        assert "spam" in spec.keywords
        assert spec.environment["CTEST_NUM_RANKS"] == "5"
        assert spec.environment["EGGS"] == "SPAM"


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
            make = Executable("make")
            make()
            file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
            specs = file.lock()
            assert len(specs) == 1
            spec = specs[0]
            assert spec.rparameters["cpus"] == 4
            assert "foo" in spec.keywords
            assert "baz" in spec.keywords


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
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        [spec] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            workspace = ExecutionSpace(Path.cwd(), Path("foo"))
            case = tc.TestCase(spec=spec, workspace=workspace)
            runner(case)
            assert case.status.name == "FAILED"
            assert case.status.code == 65


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
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        [spec] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            workspace = ExecutionSpace(Path.cwd(), Path("foo"))
            case = tc.TestCase(spec=spec, workspace=workspace)
            runner(case)
            assert case.status.name == "SKIPPED"


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
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        [spec] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            workspace = ExecutionSpace(Path.cwd(), Path("foo"))
            case = tc.TestCase(spec=spec, workspace=workspace)
            runner(case)
        assert case.status.name == "SUCCESS"
        assert case.status.code == 0


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_fixtures(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        for f in (
            "emailResults",
            "testFoo",
            "testDb",
            "testDbWithFoo",
            "initDB",
            "userCreation",
            "deleteDB",
            "removeFoos",
        ):
            touchp(f)
            set_executable(f)
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
# Example from https://cmake.org/cmake/help/latest/prop_test/FIXTURES_REQUIRED.html
add_test(testsDone   ./emailResults)
add_test(fooOnly     ./testFoo)
add_test(dbOnly      ./testDb)
add_test(dbWithFoo   ./testDbWithFoo)
add_test(createDB    ./initDB)
add_test(setupUsers  ./userCreation)
add_test(cleanupDB   ./deleteDB)
add_test(cleanupFoo  ./removeFoos)
set_tests_properties(setupUsers PROPERTIES DEPENDS createDB)
set_tests_properties(createDB   PROPERTIES FIXTURES_SETUP    DB)
set_tests_properties(setupUsers PROPERTIES FIXTURES_SETUP    DB)
set_tests_properties(cleanupDB  PROPERTIES FIXTURES_CLEANUP  DB)
set_tests_properties(cleanupFoo PROPERTIES FIXTURES_CLEANUP  Foo)
set_tests_properties(testsDone  PROPERTIES FIXTURES_CLEANUP  "DB;Foo")
set_tests_properties(fooOnly    PROPERTIES FIXTURES_REQUIRED Foo)
set_tests_properties(dbOnly     PROPERTIES FIXTURES_REQUIRED DB)
set_tests_properties(dbWithFoo  PROPERTIES FIXTURES_REQUIRED "DB;Foo")
set_tests_properties(dbOnly dbWithFoo createDB setupUsers cleanupDB PROPERTIES RESOURCE_LOCK DbAccess)
"""
            )
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        specs = file.lock()
        spec_map = {spec.name: spec for spec in specs}

        tests_done = spec_map["testsDone"]
        foo_only = spec_map["fooOnly"]
        db_only = spec_map["dbOnly"]
        db_with_foo = spec_map["dbWithFoo"]
        create_db = spec_map["createDB"]
        setup_users = spec_map["setupUsers"]
        cleanup_db = spec_map["cleanupDB"]
        cleanup_foo = spec_map["cleanupFoo"]

        assert set([_.id for _ in setup_users.dependencies]) == {create_db.id}
        assert set([_.id for _ in tests_done.dependencies]) == {
            create_db.id,
            foo_only.id,
            db_with_foo.id,
            db_only.id,
            setup_users.id,
        }
        assert foo_only.dependencies == []
        assert set([_.id for _ in db_only.dependencies]) == {create_db.id, setup_users.id}
        assert set([_.id for _ in db_with_foo.dependencies]) == {setup_users.id, create_db.id}
        assert set([_.id for _ in cleanup_db.dependencies]) == {
            db_only.id,
            db_with_foo.id,
            create_db.id,
            setup_users.id,
        }
        assert set([_.id for _ in cleanup_foo.dependencies]) == {foo_only.id, db_with_foo.id}


class Hook:
    def __init__(self, pool):
        self.pool = pool

    @canary.hookimpl
    def canary_resource_pool_types(self):
        return self.pool.types


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctest_resource_env(tmpdir):
    """Example taken from https://cmake.org/cmake/help/latest/manual/ctest.1.html#id41"""
    with working_dir(tmpdir.strpath, create=True):
        touchp("script.py")
        set_executable("script.py")
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write(
                """\
add_test(test1 "script.py")
set_tests_properties(test1 PROPERTIES RESOURCE_GROUPS "2,gpus:2;gpus:4,gpus:1,crypto_chips:2" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
"""
            )
        mkdirp("CMakeFiles")
        with open("CMakeCache.txt", "w") as fh:
            fh.write(f"PROJECT_SOURCE_DIR:INTERNAL={os.getcwd()}")

        pool = {
            "cpus": [
                {"id": "0", "slots": 1},
                {"id": "1", "slots": 1},
                {"id": "2", "slots": 1},
                {"id": "3", "slots": 1},
                {"id": "4", "slots": 1},
            ],
            "gpus": [
                {"id": "0", "slots": 2},
                {"id": "1", "slots": 4},
                {"id": "2", "slots": 2},
                {"id": "3", "slots": 1},
            ],
            "crypto_chips": [{"id": "card0", "slots": 4}],
        }
        with canary.config.override():
            mkdirp("./foo")
            pool = ResourcePool({"additional_properties": {}, "resources": pool})
            canary.config.pluginmanager.register(Hook(pool), "myhook")
            file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
            [spec] = file.lock()
            check = pool.accommodates(spec.required_resources())
            if not check:
                raise ValueError(check.reason)
            resources = pool.checkout(spec.required_resources())
            workspace = ExecutionSpace(Path.cwd(), Path("foo"))
            case = tc.TestCase(spec=spec, workspace=workspace)
            case.assign_resources(resources)
            setup_ctest(case)
            assert case.variables["CTEST_RESOURCE_GROUP_COUNT"] == "3"
            assert case.variables["CTEST_RESOURCE_GROUP_0"] == "gpus"
            assert case.variables["CTEST_RESOURCE_GROUP_1"] == "gpus"
            assert case.variables["CTEST_RESOURCE_GROUP_2"] == "crypto_chips,gpus"
            assert case.variables["CTEST_RESOURCE_GROUP_0_GPUS"] == "id:0,slots:2"
            assert case.variables["CTEST_RESOURCE_GROUP_1_GPUS"] == "id:2,slots:2"
            assert case.variables["CTEST_RESOURCE_GROUP_2_GPUS"] == "id:1,slots:4;id:3,slots:1"
            assert case.variables["CTEST_RESOURCE_GROUP_2_CRYPTO_CHIPS"] == "id:card0,slots:2"
