"""
How to integrate with CMake
===========================

The ``NVTest.cmake`` plugin integrates ``nvtest`` with CMake projects. This
plugin provides three main functions: ``add_nvtest``, ``add_nvtest_target``, and
``write_nvtest_config``.

To use the ``nvtest`` CMake integration:

1. Copy the ``NVTest.cmake`` file into your project's CMake modules directory.
2. Include the module in your ``CMakeLists.txt``:

   ```cmake
   include(NVTest)
   ```

Functions
---------

``add_nvtest``
~~~~~~~~~~~~~~

.. code-block:: cmake

   add_nvtest(
    NAME <name>
    <COMMAND <command>|SCRIPT <script>>
    [NO_DEFAULT_LINK]
    [LINK link1 [link2...]]
    [KEYWORDS kwd1 [kwd2...]]
    [DEPENDS_ON dep1 [dep2...]]
   )

Generates a ``nvtest`` named ``<name>`` in the current binary directory.  This
function is analogous to CMake's ``add_test``.

CMake generator expressions are supported.

.. rubric:: Parameters

``NAME``:
  The name of the test case.
``COMMAND``:
  Specify the test command line.  This is the command line that will be executed
  in the generated ``.pyt`` file.
``SCRIPT``:
  Don't generate the ``nvtest`` script, use this instead.
``NO_DEFAULT_LINK``:
  By default, the first argument in ``COMMAND`` is :ref:`linked
  <directive-link>` in the ``nvtest`` file.  This option disables the behavior.
``LINK``:
  Optional auxiliary files that should be :ref:`linked <directive-link>` into
  the test's execution directory.
``KEYWORDS``:
  Optional test :ref:`keywords <directive-keywords>`.
``DEPENDS_ON``:
  Optional test :ref:`dependencies <directive-depends-on>`.

Exactly one of ``COMMAND`` or ``SCRIPT`` must be provided.

.. rubric:: Example

.. code-block:: cmake

   add_executable(my_test my_test.cxx)
   add_nvtest(NAME my_test COMMAND my_test --option=value KEYWORDS fast unit_test)

would generate the following file in the current binary directory

.. code-block:: python

   #!/usr/bin/env python3
   # my_test.pyt
   import sys
   import nvtest
   nvtest.directives.keywords("fast", "unit_test")
   nvtest.directives.link("my_test")
   def test():
       cmd = nvtest.Executable("my_test")
       args = ["--option=value"]
       cmd(*args, allow_failure=True)
       if cmd.returncode != 0:
           raise nvtest.TestFailed("my_test")

``add_parallel_nvtest``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_parallel_nvtest(
    NAME <name>
    COMMAND <command>
    NPROC <np1 [np2...]>
    [NO_DEFAULT_LINK]
    [LINK link1 [link2...]]
    [KEYWORDS kwd1 [kwd2...]]
    [DEPENDS_ON dep1 [dep2...]]
   )

Generates a ``nvtest`` named ``<name>`` in the current binary directory that is
parameterized on the number of processors.  Parallel jobs are launched using the
value of `MPIEXEC_EXECUTABLE
<https://cmake.org/cmake/help/latest/module/FindMPI.html#variables-for-using-mpi>`_.

CMake generator expressions are supported.

.. rubric:: Parameters

``NAME``:
  The name of the test case.
``COMMAND``:
  Specify the test command line.  This is the command line that will be executed
  in the generated ``.pyt`` file.
``NPROC``:
  Number of processors to run the test on.
``NO_DEFAULT_LINK``:
  By default, the first argument in ``COMMAND`` is :ref:`linked
  <directive-link>` in the ``nvtest`` file.  This option disables the behavior.
``LINK``:
  Optional auxiliary files that should be :ref:`linked <directive-link>` into
  the test's execution directory.
``KEYWORDS``:
  Optional test :ref:`keywords <directive-keywords>`.
``DEPENDS_ON``:
  Optional test :ref:`dependencies <directive-depends-on>`.

.. rubric:: Example

.. code-block:: cmake

   add_executable(my_parallel_test my_parallel_test.cxx)
   add_parallel_nvtest(
     NAME my_parallel_test
     COMMAND my_parallel_test --option=value
     NPROC 1 4
     KEYWORDS fast unit_test
   )

would generate the following file in the current binary directory

.. code-block:: python

   #!/usr/bin/env python3
   # my_parallel_test.pyt
   import sys
   import nvtest
   nvtest.directives.keywords("fast", "unit_test")
   nvtest.directives.link("my_test")
   nvtest.directives.parameterize("np", [1, 4])
   def test():
       self = nvtest.test.instance
       mpi = nvtest.Executable("${MPIEXEC_EXECUTABLE}")
       args = ["${MPIEXEC_NUMPROC_FLAG}", self.parameters.np, "my_parallel_test", "--option=value"]
       mpi(*args, allow_failure=True)
       if mpi.returncode != 0:
           raise nvtest.TestFailed("my_parallel_test")

.. note::

    The values of ``${MPIEXEC_EXECUTABLE}`` and ``${MPIEXEC_NUMPROC_FLAG}`` are
    expanded in the actual test file.

.. note::

   If the variables ``MPIEXEC_EXECUTABLE_OVERRIDE`` and/or
   ``MPIEXEC_NUMPROC_FLAG_OVERRIDE`` are defined, they are preferred over the
   standard values of ``${MPIEXEC_EXECUTABLE}`` and ``${MPIEXEC_NUMPROC_FLAG}``.
   This is useful, for example, when the tests will run in a queuing system and
   need to be run with ``srun`` or ``jsrun``.


``add_nvtest_target``
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_nvtest_target()

Adds a make target "nvtest" to the project.  When invoked in the build directory
``nvtest -w`` is executed.

.. rubric:: Example

In your ``CMakeLists.txt`` add

.. code-block:: cmake

    add_nvtest_target()

and then

.. code-block:: console

   cd BUILD_DIR
   cmake [OPTIONS] $SOURCE_DIR
   make
   make vvtest
   make install

.. _write-nvtest-config:

``write_nvtest_config``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   write_nvtest_config()

Generates a ``nvtest.cfg`` configuration file in the project's build directory.
The configuration populates the :ref:`build section <config-file>` of the
configuration file.

``add_nvtest_options``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_nvtest_options(ON_OPTION <opt1 [opt2...]>)

Add options to the ``build:options`` configuration setting.

.. rubric:: Example

.. code-block:: cmake

   add_nvtest_options(ON_OPTION feature1 feature2)

would cause the following to be written to the build configuration
(:ref:`write-nvtest-config` must be called):

.. code-block:: ini

   [build:options]
   feature1 = true
   feature2 = true

"""

import importlib.resources
import os

import _nvtest.util.executable as ex
import _nvtest.util.filesystem as fs
import pytest

f1 = fs.which("gcc") or os.getenv("CC")
f2 = fs.which("cmake")
nvf = str(importlib.resources.files("_nvtest").joinpath("../nvtest/tools/NVTest.cmake"))
good = f1 is not None and f2 is not None and os.path.exists(nvf)


@pytest.mark.skipif(not good, reason="gcc and/or cmake not on PATH")
def test_cmake_integration(tmpdir):
    from _nvtest.main import NVTestCommand

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("baz.pyt", "w") as fh:
            fh.write("def test():\n    return 0\ntest()\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write(f"include({nvf})\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_nvtest(NAME foo COMMAND foo)\n")
            fh.write("add_nvtest(NAME baz SCRIPT baz.pyt)\n")
        with fs.working_dir("build", create=True):
            cmake = ex.Executable("cmake")
            cmake("..")
            assert os.path.exists("foo.pyt")
            assert os.path.exists("baz.pyt")
            make = ex.Executable("make")
            make()
            run = NVTestCommand("run")
            run("-w", ".")
            assert os.path.exists("TestResults/foo")
            assert os.path.exists("TestResults/baz")


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
            run = NVTestCommand("run")
            run("-w", ".")
            assert os.path.exists("TestResults/foo.np=4")


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
                assert 'args.extend(["-x", str(self.parameters.np)])' in lines
