.. _parameterizing:

How to parameterize tests
=========================

A single test script can generate many test instances, each having different parameters, using the :ref:`parameterize <directive-parameterize>` directive.  The test script uses the parameter name[s] and value[s] to run variations of the test.  For example, the test script

.. code-block:: python

   # test.pyt
   import sys
   import nvtest

   nvtest.mark.parameterize("MODEL", (1, 2))


   def test():
      self = nvtest.test.instance
      print(f"{self.parameters.MODEL}")


   if __name__ == "__main__":
      sys.exit(test())

will produce two test instances, one with ``[MODEL=1]`` and another with ``[MODEL=2]``, each executed in their own test directory:

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   2 test cases:
   ├── test[MODEL=1]
   └── test[MODEL=2]

This same script, implemented as a ``.vvt`` test type looks like:

.. code-block:: python

   # test.vvt
   import sys
   import vvtest_util as vvt

   # VVT: parameterize : MODEL = 1,2

   def test():
      print(f"{vvt.MODEL}")


   if __name__ == "__main__":
      sys.exit(test())

Multiple parameter names and their values can be defined:

.. code-block:: python

   import nvtest
   nvtest.mark.parameterize("MODEL,YIELD", [(1, 1.e5), (2, 1.e6), (3, 1.e7)])

which would result in the following three tests

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   3 test cases:
   ├── test[MODEL=1,YIELD=100000.0]
   ├── test[MODEL=2,YIELD=1.000000e+06]
   └── test[MODEL=3,YIELD=1.000000e+07]

If multiple ``parameterize`` directives are specified, the cartesian product of parameters is performed:

.. code-block:: python

   import nvtest

   nvtest.mark.parameterize("MODEL", (1, 2))
   nvtest.mark.parameterize("YIELD", (1.e5, 1.e6, 1.e7))

   def test():
       self = nvtest.test.instance
       model, yld = self.parameters.model, self.parameters.YIELD
       print(f"running test with MODEL={model} and YIELD={yld}")

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   6 test cases:
   ├── test[MODEL=1,YIELD=100000.0]
   ├── test[MODEL=1,YIELD=1.000000e+06]
   ├── test[MODEL=1,YIELD=1.000000e+07]
   ├── test[MODEL=2,YIELD=100000.0]
   ├── test[MODEL=2,YIELD=1.000000e+06]
   └── test[MODEL=2,YIELD=1.000000e+07]


Similarly,

.. code-block:: python

   import nvtest

   nvtest.mark.parameterize("MODEL,YIELD", [(1, 1e5), (2, 1e6), (3, 1e7)])
   nvtest.mark.parameterize("np", (4, 8))

   def test():
       ...

results in the following 6 test cases:

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   6 test cases:
   ├── foo[MODEL=1,YIELD=100000.0,np=4]
   ├── foo[MODEL=1,YIELD=100000.0,np=8]
   ├── foo[MODEL=2,YIELD=1.000000e+06,np=4]
   ├── foo[MODEL=2,YIELD=1.000000e+06,np=8]
   ├── foo[MODEL=3,YIELD=1.000000e+07,np=4]
   └── foo[MODEL=3,YIELD=1.000000e+07,np=8]

vvt parameter types
-------------------

In ``.vvt`` file types, parameters are read in by a json reader.  In general, numbers are parsed as numbers and anything that can't be cast to a number is left as a string.

Test execution directories
--------------------------

Test instances are executed in their own test directories.

.. code-block:: console

   $ nvtest run .
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   Maximum subprocess workers: auto
   Test results directory: ./TestResults
   search paths:
   .
   ============================== Setting up test session ==============================
   collected 2 tests from 1 files in 0.26s.
   running 2 test cases from 1 files
   skipping 0 test cases
   =============================== Beginning test session ==============================
   STARTING: test[MODEL=1]
   STARTING: test[MODEL=2]
   FINISHED: test[MODEL=1] PASS
   FINISHED: test[MODEL=2] PASS
   ================================== 2 pass in 0.34s. =================================
