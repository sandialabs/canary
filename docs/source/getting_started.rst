Getting started
===============

``nvtest`` is a framework for writing and running tests and is developed to test finite element and other scientific applications.  A test is an executable script with extension ``.pyt`` or ``.vvt``.  ``nvtest``'s methodology is simple: given a path on the filesystem, recursively search it for test files having ``.pyt`` or ``.vvt`` extensions and execute them.  If the exit code from executed test file is ``0``, the test is considered to have ``passed``, it is considered to have ``diffed`` if the exit code is 64, or ``failed`` otherwise.  ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``nvtest`` ecosystem.


``nvtest`` has several subcommands.  To get the list of subcommands, issue

.. code-block:: console

   nvtest -h

To get help on an individual subcommand, issue

.. code-block:: console

   nvtest SUBCOMMAND -h


A first test
------------

In this first test, a function that adds two numbers is verified for correctness.

.. code:: python

   # contents of test_1.pyt
   import sys

   def add(a: int, b: int) -> int:
       return a + b


   def test() -> int:
       assert add(2, 3) == 5
       return 0

   if __name__ == "__main__":
       sys.exit(test())

To execute it:

.. code:: console

   $ nvtest run
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   Maximum subprocess workers: auto
   Test results directory: ./TestResults
   search paths:
   .
   ============================== Setting up test session ==============================
   collected 1 tests from 1 files in 0.16s.
   running 1 test cases from 1 files
   skipping 0 test cases
   =============================== Beginning test session ==============================
   STARTING: test_1
   FINISHED: test_1 PASS
   ================================== 1 pass in 0.14s. =================================


A second test
-------------

In this second test, the external program "``my-app``" is executed and output verified for correctness.

.. code:: python

   # contents of test_2.pyt
   import sys
   import nvtest


   def test() -> int:
       exe = nvtest.Executable("./my-app")
       exe()
       assert exe.returncode == 0
       return 0

   if __name__ == "__main__":
       sys.exit(test())

To execute it:

.. code:: console

   $ nvtest run
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   Maximum subprocess workers: auto
   Test results directory: ./TestResults
   search paths:
   .
   ============================== Setting up test session ==============================
   collected 1 tests from 1 files in 0.16s.
   running 1 test cases from 1 files
   skipping 0 test cases
   =============================== Beginning test session ==============================
   STARTING: test_2
   FINISHED: test_2 PASS
   ================================== 1 pass in 0.14s. =================================
