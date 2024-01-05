The test results directory
==========================

Once collected, tests are run in a separate execution directory (default: ``./TestResults``).  Each test is run in its own subdirectory with the following naming scheme:

.. code-block:: console

    $path/$name

where ``$path`` is the directory name (including parents), relative to the search path, of the test file, and ``$name`` is the basename of the test.  Consider the search path

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
           │   nvtest-out.txt
           │   test_1.pyt -> ../../../../tests/regressions/2D/test_1.pyt
           └── test_2
               ├── nvtest-out.txt
               └── test_2.pyt -> ../../../../tests/regressions/2D/test_2.pyt

The test's script is symbolically linked into the execution directory, where it is ultimately executed.  The file ``nvtest-out.txt`` is the output from running the test.
