.. _cmake-integration:

How to integrate with CMake
===========================

The ``NVTest.cmake`` plugin integrates ``nvtest`` with CMake projects. This plugin provides three main functions: ``add_nvtest``, ``add_nvtest_target``, and ``write_nvtest_config``.

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
   )

Generates a ``nvtest`` named ``<name>`` in the current binary directory.  This function is analogous to CMake's ``add_test``.

CMake generator expressions are supported.

.. rubric:: Parameters

``NAME``:
  The name of the test case.
``COMMAND``:
  Specify the test command line.  This is the command line that will be executed in the generated ``.pyt`` file.
``SCRIPT``:
  Don't generate the ``nvtest`` script, use this instead.
``NO_DEFAULT_LINK``:
  By default, the first argument in ``COMMAND`` is :ref:`linked <directive-link>` in the ``nvtest`` file.  This option disables the behavior.
``LINK``:
  Optional auxiliary files that should be :ref:`linked <directive-link>` into the test's execution directory.
``KEYWORDS``:
  Optional test :ref:`keywords <directive-keywords>`.

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
   nvtest.mark.keywords("fast", "unit_test")
   nvtest.mark.link("my_test")
   def test():
       cmd = nvtest.Executable("my_test --option=value")
       cmd(allow_failure=True)
       if cmd.returncode != 0:
           raise nvtest.TestFailed("my_test")

```add_nvtest_target```
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_nvtest_target()

Adds a make target "nvtest" to the project.  When invoked in the build directory ``nvtest -w`` is executed.

``write_nvtest_config``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   write_nvtest_config()

Generates a ``nvtest.cfg`` configuration file in the project's build directory.

``add_nvtest_options``
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_nvtest_options(ON_OPTION <opt1 [opt2...]>)

Add options to the ``build:options`` configuration setting.
