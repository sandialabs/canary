.. _parameterizing:

How to parameterize tests
=========================

A single test file can generate many test cases, each having different parameters, using the :ref:`parameterize <directive-parameterize>` directive.  The test file uses the parameter name[s] and value[s] to run variations of the test.  For example, the test script

``.pyt``:

.. code-block:: python

   # test.pyt
   import sys
   import nvtest

   nvtest.directives.parameterize("a", (1, 4))

   def test():
      self = nvtest.test.instance
      print(f"{self.parameters.a}")

   if __name__ == "__main__":
      sys.exit(test())

``.vvt``:

.. code-block:: python

   # test.pyt
   #VVT: parameterize : a = 1 4
   import sys
   import vvtest_util as vvt

   def test():
      print(f"{vvt.a}")

   if __name__ == "__main__":
      sys.exit(test())

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   2 test cases:
   ├── test[a=1]
   └── test[a=4]

Multiple parameter names and their values can be defined:

.. code-block:: python

   import nvtest
   nvtest.directives.parameterize("a,b", [(1, 1.e5), (4, 1.e6), (16, 1.e7)])

which would result in the following three tests

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   3 test cases:
   ├── test[a=1,b=100000]
   ├── test[a=4,b=1e+06]
   └── test[a=16,b=1e+07]

If multiple ``parameterize`` directives are specified, the cartesian product of parameters is performed:

.. code-block:: python

   import nvtest

   nvtest.directives.parameterize("a", (1, 4))
   nvtest.directives.parameterize("b", (1.e5, 1.e6, 1.e7))

   def test():
       self = nvtest.test.instance
       a, b = self.parameters.model, self.parameters.b
       print(f"running test with a={a} and b={b}")

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   6 test cases:
   ├── test[a=1,b=100000]
   ├── test[a=1,b=1e+06]
   ├── test[a=1,b=1e+07]
   ├── test[a=4,b=100000]
   ├── test[a=4,b=1e+06]
   └── test[a=4,b=1e+07]


Similarly,

.. code-block:: python

   import nvtest

   nvtest.directives.parameterize("a,b", [(1, 1e5), (2, 1e6), (3, 1e7)])
   nvtest.directives.parameterize("np", (4, 8))

   def test():
       ...

results in the following 6 test cases:

.. code-block:: console

   $ nvtest describe test.pyt
   --- test ------------
   File: .../test.pyt
   Keywords:
   6 test cases:
   ├── foo[a=1,b=100000,np=4]
   ├── foo[a=1,b=100000,np=8]
   ├── foo[a=2,b=1e+06,np=4]
   ├── foo[a=2,b=1e+06,np=8]
   ├── foo[a=3,b=1e+07,np=4]
   └── foo[a=3,b=1e+07,np=8]

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
   STARTING: test[a=1]
   STARTING: test[a=2]
   FINISHED: test[a=1] PASS
   FINISHED: test[a=2] PASS
   ================================== 2 pass in 0.34s. =================================
