The test session
================

Phases of a test session
------------------------

A test session consists of the following phases:

Discovery:
  Search for test scripts in a test suite.

Setup:
  Order test scripts, create unique execution directories for each test, and copy/link necessary resources into the execution directory.

Run:
  For each test, move to its execution directory and run the test script, first ensuring that dependencies have been satisfied.

Cleanup:
  Remove artifacts created by the test.

Test session execution
----------------------

When ``nvtest run PATH`` is executed, ``PATH`` is searched for test files and the session begun.  Once collected, tests are run in a separate execution directory (default: ``./TestResults``).  Each test is run in its own subdirectory with the following naming scheme:

.. code-block:: console

    TestResults/$path/$name.p1=v1.p2=v2...pn=vn

where ``$path`` is the directory name (including parents), relative to the search path, of the test file, and ``$name`` is the basename of the test. The ``px=vx`` are the names of values of the test parameters (if any).

Consider, for example, the search path

.. code-block:: console

   $ tree tests
   tests/
   └── regression
       └── 2D
           ├── test_1.pyt
           └── test_2.pyt

and the corresponding test results directory tree:

.. code-block:: console

   $ tree TestResults
   TestResults/
   └── regression
       └── 2D
           ├── test_1
           │   ├── nvtest-out.txt
           │   └── test_1.pyt -> ../../../../tests/regressions/2D/test_1.pyt
           └── test_2
               ├── nvtest-out.txt
               └── test_2.pyt -> ../../../../tests/regressions/2D/test_2.pyt

The test's script is symbolically linked into the execution directory, where it is ultimately executed.  The file ``nvtest-out.txt`` is the output from running the test.
