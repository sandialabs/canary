.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _integrations-cmake:

Integrate with CMake
====================

The ``Canary.cmake`` plugin integrates ``canary`` with CMake projects. This
plugin provides three main functions: ``add_canary_test``, ``add_canary_target``, and
``write_canary_config``.

To use the ``canary`` CMake integration:

1. Copy the ``Canary.cmake`` file into your project's CMake modules directory.
2. Include the module in your ``CMakeLists.txt``:

   .. code-block:: cmake

      include(Canary)

Functions
---------

``add_canary_test``
~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_canary_test(
    NAME <name>
    <COMMAND <command>|SCRIPT <script>>
    [NO_DEFAULT_LINK]
    [LINK link1 [link2...]]
    [KEYWORDS kwd1 [kwd2...]]
    [DEPENDS_ON dep1 [dep2...]]
   )

Generates a ``canary`` named ``<name>`` in the current binary directory.  This
function is analogous to CMake's ``add_test``.

CMake generator expressions are supported.

.. rubric:: Parameters

``NAME``:
  The name of the test case.
``COMMAND``:
  Specify the test command line.  This is the command line that will be executed
  in the generated ``.pyt`` file.
``SCRIPT``:
  Don't generate the ``canary`` script, use this instead.
``NO_DEFAULT_LINK``:
  By default, the first argument in ``COMMAND`` is :ref:`linked
  <directive-link>` in the ``canary`` file.  This option disables the behavior.
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
   add_canary_test(NAME my_test COMMAND my_test --option=value KEYWORDS fast unit_test)

would generate the following file in the current binary directory

.. code-block:: python

   #!/usr/bin/env python3
   # my_test.pyt
   import sys
   import canary
   canary.directives.keywords("fast", "unit_test")
   canary.directives.link("my_test")
   def test():
       cmd = canary.Executable("my_test")
       args = ["--option=value"]
       cmd(*args, fail_on_error=False)
       if cmd.returncode != 0:
           raise canary.TestFailed("my_test")

``add_parallel_canary_test``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_parallel_canary_test(
    NAME <name>
    COMMAND <command>
    NPROC <np1 [np2...]>
    [NO_DEFAULT_LINK]
    [LINK link1 [link2...]]
    [KEYWORDS kwd1 [kwd2...]]
    [DEPENDS_ON dep1 [dep2...]]
   )

Generates a ``canary`` named ``<name>`` in the current binary directory that is
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
  <directive-link>` in the ``canary`` file.  This option disables the behavior.
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
   add_parallel_canary_test(
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
   import canary
   canary.directives.keywords("fast", "unit_test")
   canary.directives.link("my_test")
   canary.directives.parameterize("cpus", [1, 4])
   def test():
       self = canary.test.instance
       mpi = canary.Executable("${MPIEXEC_EXECUTABLE}")
       args = ["${MPIEXEC_NUMPROC_FLAG}", self.parameters.cpus, "my_parallel_test", "--option=value"]
       mpi(*args, fail_on_error=False)
       if mpi.returncode != 0:
           raise canary.TestFailed("my_parallel_test")

.. note::

    The values of ``${MPIEXEC_EXECUTABLE}`` and ``${MPIEXEC_NUMPROC_FLAG}`` are
    expanded in the actual test file.

.. note::

   If the variables ``MPIEXEC_EXECUTABLE_OVERRIDE`` and/or
   ``MPIEXEC_NUMPROC_FLAG_OVERRIDE`` are defined, they are preferred over the
   standard values of ``${MPIEXEC_EXECUTABLE}`` and ``${MPIEXEC_NUMPROC_FLAG}``.
   This is useful, for example, when the tests will run in a queuing system and
   need to be run with ``srun`` or ``jsrun``.


``add_canary_target``
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_canary_target()

Adds a make target "canary" to the project.  When invoked in the build directory
``canary -w`` is executed.

.. rubric:: Example

In your ``CMakeLists.txt`` add

.. code-block:: cmake

    add_canary_target()

and then

.. code-block:: console

   cd BUILD_DIR
   cmake [OPTIONS] $SOURCE_DIR
   make
   make canary
   make install

.. _cdash-write-config:

``write_canary_config``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   write_canary_config()

Generates a ``canary.cfg`` configuration file in the project's build directory.
The configuration populates the :ref:`build section <configuration>` of the
configuration file.

``add_canary_options``
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_canary_options(ON_OPTION <opt1 [opt2...]>)

Add options to the ``build:options`` configuration setting.

.. rubric:: Example

.. code-block:: cmake

   add_canary_options(ON_OPTION feature1 feature2)

would cause the following to be written to the build configuration
(:ref:`cdash-write-config` must be called):

.. code-block:: yaml

   build:
     options:
       feature1: true
       feature2: true
