Getting started
===============

A first test
------------

In this first test, the test file ``test_1.pyt`` defines a function that adds two numbers and verifies it for correctness.

.. literalinclude:: /pyt/first_test/test_1.pyt
   :language: python

To run the test, navigate to the directory containing ``test_1.pyt`` and run the command

.. code:: console

   nvtest run

Messages like those below will be printed to the scrren:

.. code:: console

   ------------------------- Setting up test session -------------------------
   macos -- Python 3.11.7
   Available cpus: 10
   Available cpus per test: 10
   Maximum number of asynchronous jobs: 10
   Working tree: ...
   search paths:
     .
   collected 1 tests from 1 files in 0.05s.
   running 1 test cases from 1 files
   skipping 0 test cases
   -------------------------- Beginning test session -------------------------
   STARTING: 4e70ffa test_1
   FINISHED: 4e70ffa test_1 PASS
   ----------------------------- 1 pass in 0.28s. ----------------------------

A second test
-------------

In this second, somewhat contrived, test, the external program "``my-add``" adds two numbers and writes the result to the console's stdout.  The test executes the script, reads it output, and verifies correctness.

Contents of ``my-add``:

.. literalinclude:: /pyt/second_test/my-add
   :language: python

The test script:

.. literalinclude:: /pyt/second_test/test_my_add.pyt
   :language: python

This test introduces two new features:

* ``nvtest.directives.link`` links ``my-add`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``nvtest.Executable`` which provides a wrapper around executable scripts.

To run the test, navigate to the folder containing the script and test file and run the command:

.. code:: console

   nvtest run

.. code:: console

   ------------------------- Setting up test session -------------------------
   macos -- Python 3.11.7
   Available cpus: 10
   Available cpus per test: 10
   Maximum number of asynchronous jobs: 10
   Working tree: ...
   search paths:
     .
   collected 1 tests from 1 files in 0.05s.
   running 1 test cases from 1 files
   skipping 0 test cases
   -------------------------- Beginning test session -------------------------
   STARTING: 4e70ffa test_my_add
   FINISHED: 4e70ffa test_my_add PASS
   ----------------------------- 1 pass in 0.28s. ----------------------------
