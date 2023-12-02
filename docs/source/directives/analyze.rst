.. _directive-analyze:

analyze
=======

Create a test instance that depends on all parameterized test instances and run it after they have completed.

.. code-block:: python

   analyze(arg=True, *, flag=None, script=None, options=None, platforms=None, testname=None)

.. code-block:: python

   #VVT: analyze (options=..., platforms=..., testname=...) : (flag|script)

Parameters
----------

* ``flag``: Run the test script with the ``--FLAG`` option on the command line.  ``flag`` should start with a hyphen (``-``).  The script should parse this value and perform the appropriate analysis.
* ``script``: Run ``script`` during the analysis phase (instead of the test file).
* ``testname``: Restrict processing of the directive to this test name
* ``platforms``: Restrict processing of the directive to certain platform or platforms
* ``options``: Restrict processing of the directive to command line ``-o`` options
* ``parameters``: Restrict processing of the directive to certain parameter names and values

References
----------

* :ref:`Writing an execute/analyze test <Writing-an-execute-analyze-test>`

Examples
--------

.. code-block:: python

   import nvtest
   nvtest.directives.analyze(flag="--analyze", platforms="not darwin")
   nvtest.directives.parameterize("a,b", [(1, 2), (3, 4)])

.. code-block:: python

   # VVT: analyze (platforms="not darwin") : --analyze
   # VVT: parameterize : a,b = 1,2 3,4

will run an analysis job after jobs ``[a=1,b=3]`` and ``[a=2,b=4]`` have run to completion.  The ``nvtest.test.instance`` and ``vvtest_util`` modules will contain information regarding the previously run jobs so that a collective analysis can be performed.

For either file type, the script must query the command line arguments to determine the type of test to run:

.. code-block:: python

   import argparse
   import sys

   import nvtest
   nvtest.directives.analyze(flag="--analyze", platforms="not darwin")
   nvtest.directives.parameterize("a,b", [(1, 2), (3, 4)])


   def test() -> int:
       ...

   def analyze() -> int:
       ...

   def main() -> int:
       parser = argparse.ArgumentParser()
       parser.add_argument("--analyze", action="store_true")
       args = parser.parse_args()
       if args.analyze:
           return analyze()
       return test()


   if __name__ == "__main__":
       sys.exit(main())
