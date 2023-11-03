Getting started
===============

``nvtest`` is a framework for writing and running tests.  A test is an executable script with extension ``.pyt`` or ``.vvt`` and are most often used to test finite element and other scientific applications.  Tests are considered to have ``passed`` if the script's exit code is 0, ``diffed`` if the exit code is 64, or ``failed`` otherwise.  ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written is Python can take advantage of the full ``nvtest`` ecosystem.

``nvtest`` has many subcommands.  To get the list of subcommands, issue

.. code-block:: console

   nvtest -h

To get help on an individual subcommand, issue

.. code-block:: console

   nvtest SUBCOMMAND -h

A first test
------------

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
