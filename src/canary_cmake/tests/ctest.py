# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import threading

import pytest

import canary
from _canary.queue import ResourceQueue
from _canary.resource_pool import ResourcePool
from _canary.util.executable import Executable
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import set_executable
from _canary.util.filesystem import touchp
from _canary.util.filesystem import which
from _canary.util.filesystem import working_dir
from canary_cmake.ctest import CTestTestGenerator


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, case):
        try:
            case.setup()
            case.run(qsize=1, qrank=0)
        finally:
            case.finish()


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
        cases = file.lock()
        assert len(cases) == 2

        case = cases[0]
        assert case.cpus == 5
        assert case.gpus == 5
        assert "foo" in case.keywords
        assert "baz" in case.keywords
        command = case.command()
        command[0] = os.path.basename(command[0])
        assert command == ["script.sh", "some-exe"]
        assert case.variables["CTEST_NUM_RANKS"] == "5"
        assert case.variables["SPAM"] == "BAZ"

        case = cases[1]
        command = case.command()
        command[0] = os.path.basename(command[0])
        assert command == ["mpiexec", "-n", "4", "some-exe"]
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
            make = Executable("make")
            make()
            file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
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
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        [case] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            case.set_workspace_properties(workspace=f"{os.getcwd()}/foo", session=None)
            runner(case)
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
        file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
        [case] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            case.set_workspace_properties(workspace=f"{os.getcwd()}/foo", session=None)
            runner(case)


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
        [case] = file.lock()
        mkdirp("./foo")
        runner = Runner()
        with canary.config.override():
            case.set_workspace_properties(workspace=f"{os.getcwd()}/foo", session=None)
            runner(case)
        assert case.status == "success"
        assert case.returncode == 1


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
        cases = file.lock()
        case_map = {case.name: case for case in cases}
        print(case_map)

        tests_done = case_map["testsDone"]
        foo_only = case_map["fooOnly"]
        db_only = case_map["dbOnly"]
        db_with_foo = case_map["dbWithFoo"]
        create_db = case_map["createDB"]
        setup_users = case_map["setupUsers"]
        cleanup_db = case_map["cleanupDB"]
        cleanup_foo = case_map["cleanupFoo"]

        assert set(setup_users.dependencies) == {create_db}
        assert set(tests_done.dependencies) == {
            create_db,
            foo_only,
            db_with_foo,
            db_only,
            setup_users,
        }
        assert foo_only.dependencies == []
        assert set(db_only.dependencies) == {create_db, setup_users}
        assert set(db_with_foo.dependencies) == {setup_users, create_db}
        assert set(cleanup_db.dependencies) == {db_only, db_with_foo, create_db, setup_users}
        assert set(cleanup_foo.dependencies) == {foo_only, db_with_foo}


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
            file = CTestTestGenerator(os.getcwd(), "CTestTestfile.cmake")
            [case] = file.lock()
            case.set_workspace_properties(workspace=f"{os.getcwd()}/foo", session=None)
            check = pool.accommodates(case.required_resources())
            if not check:
                raise ValueError(check.reason)
            case.status.set("ready")
            queue = ResourceQueue(lock=threading.Lock(), resource_pool=pool)
            queue.put(case)
            queue.prepare()
            _, c = queue.get()
            assert isinstance(c, canary.TestCase)
            with c.rc_environ():
                assert os.environ["CTEST_RESOURCE_GROUP_COUNT"] == "3"
                assert os.environ["CTEST_RESOURCE_GROUP_0"] == "gpus"
                assert os.environ["CTEST_RESOURCE_GROUP_1"] == "gpus"
                assert os.environ["CTEST_RESOURCE_GROUP_2"] == "crypto_chips,gpus"
                assert os.environ["CTEST_RESOURCE_GROUP_0_GPUS"] == "id:0,slots:2"
                assert os.environ["CTEST_RESOURCE_GROUP_1_GPUS"] == "id:2,slots:2"
                assert os.environ["CTEST_RESOURCE_GROUP_2_GPUS"] == "id:1,slots:4;id:3,slots:1"
                assert os.environ["CTEST_RESOURCE_GROUP_2_CRYPTO_CHIPS"] == "id:card0,slots:2"
