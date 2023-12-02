.. _writing-an-execute-analyze-test:

How to write an execute and analyze test
========================================

An execute/analyze test is one that uses parameters to expand into multiple test instances, followed by a final test instance that analyzes the results. Naturally, the analyze test only runs after all the parameter tests are finished. This execute/analyze pattern is useful, for example, in performing a rate of convergence study.

Like a normal parameterized test, the test script itself is used to execute each of the test instances. The addition of the directive

``.pyt``

.. code-block:: python

   import nvtest
   nvtest.directives.analyze(script="analyze.py)

``.vvt``:

.. code-block:: python

   #VVT: analyze : analyze.py

signals to the test harness that this is an execute/analyze test and will create a separate test for performing the analysis (in this case by running the given script name).

Consider the test file ``converge.pyt``:

.. code:: python

   import nvtest
   nvtest.directives.parameterize("dh", (0.2, 0.01, 0.005))
   nvtest.directives.analyze(script="converge.py")
   self = nvtest.test.instance
   print(f"executing {self.name} parameters {self.parameters}")

``converge.vvt``:

.. code:: python

   #VVT: parameterize : dh = 0.2 0.01 0.005
   #VVT: analyze : converge.py
   import vvtest_util as vvt
   print(f"executing {vvt.NAME} parameters {vvt.PARAM_DICT}")

and the analyze script called ``converge.py``

.. code:: python

   #!/usr/bin/env python
   import vvtest_util as vvt
   print(f"analyzing {vvt.NAME}")
   print(f"dh parameter values = {vvt.PARAM_dh}")

When this test is run, we get

.. code-block:: console

   $ nvtest
   ...
   ==================================================
   converge             Exit    pass     1s   07/05 19:42:00 TestResults.Darwin/converge
   converge             Exit    pass     1s   07/05 19:41:59 TestResults.Darwin/converge.dh=0.005
   converge             Exit    pass     1s   07/05 19:41:59 TestResults.Darwin/converge.dh=0.01
   converge             Exit    pass     1s   07/05 19:41:59 TestResults.Darwin/converge.dh=0.2
   ==================================================
   Summary: 4 pass, 0 timeout, 0 diff, 0 fail, 0 notrun, 0 notdone

   Finish date: Tue Jul  5 19:42:01 2016 (elapsed time 2s)
   Test directory: TestResults.Darwin

Notice that along with the normal parameterized test names, there is a test name that does not have parameters appended. This is the execution of the analyze test. The output of one of the parameter tests and of the analyze test is this:

.. code-block:: console

   $ cat TestResults.Darwin/converge.dh=0.2/execute.log
   Starting test: converge
   Directory    : /Users/rrdrake/vvtdoc/ex13/TestResults.Darwin/converge.dh=0.2
   Command      : /usr/bin/env python converge.vvt
   Timeout      : 3600

   Cleaning execute directory...
   Linking and copying working files...
   ln -s /Users/rrdrake/vvtdoc/ex13/converge.vvt converge.vvt

   executing converge : parameters {'dh': '0.2'}
   s968057%
   s968057% cat TestResults.Darwin/converge/execute.log
   Starting test: converge
   Directory    : /Users/rrdrake/vvtdoc/ex13/TestResults.Darwin/converge
   Command      : /usr/bin/env python converge.py
   Timeout      : 3600

   Cleaning execute directory...
   Linking and copying working files...
   ln -s /Users/rrdrake/vvtdoc/ex13/converge.vvt converge.vvt
   ln -s /Users/rrdrake/vvtdoc/ex13/converge.py converge.py

   analyzing converge
   parameters for dh = ['0.2', '0.01', '0.005']

Note how the parameter names and values of the "children" tests are provided in ``PARAM_*`` variables. These variables can be used to construct the directory name of the children in order to access the output from their executions. In this case, you could do the following to construct the directory names:

.. code:: python

   for dh in PARAM_dh:
       xdir = f"../converge.dh={dh}"
       print (f"xdir {xdir}")
       assert os.path.exists(xdir)

Finally, note that the exit status of the analyze test is no different than any other test. You can exit diff or raise an Exception, or exit cleanly for a pass.

Using the test script itself for the analyze
--------------------------------------------

In the previous example, we used an external file to be run for the analysis. You can instead, use the test file itself. This is done by specifying an option to be given to the test script instead of a file name. For example,

``.pyt``:

.. code-block:: python

   import nvtest
   nvtest.directives.analyze(flag="--analyze")

``.vvt``:

.. code-block:: python

   #VVT: analyze : --analyze

The option name can be anything, except that it must start with a dash.  When the test script is launched for the parameter tests, no option is passed in. But when the script is launched for the analyze, the specified option will be placed on the command line.  Our previous example could be modified as follows:

``.pyt``:

.. code:: python

   import argparse
   import sys
   import nvtest

   nvtest.directives.parameterize("dh", (0.2, 0.01, 0.005))
   nvtest.directives.analyze(flag="--analyze")

   def main():
       p = argparse.ArgumentParser()
       p.add_argument("--analyze", action="store_true")
       args = p.parse_args()
       if args.analyze:
           # this is a parameter test
           print(f"executing {vvt.NAME} parameters {vvt.PARAM_DICT}")
       else:
           # this is the analyze test
           print(f"analyzing {vvt.NAME}")
           print(f"parameters for dh = {vvt.PARAM_dh}")
           for dh in vvt.PARAM_dh:
               xdir = f"../converge2.dh={dh}"
               print(f"xdir {xdir}")
               assert os.path.exists(xdir)

``.vvt``:

.. code:: python

   #VVT: parameterize : dh = 0.2 0.01 0.005
   #VVT: analyze : --analyze
   import argparse
   import sys
   import vvtest_util as vvt
   def main():
       p = argparse.ArgumentParser()
       p.add_argument("--analyze", action="store_true")
       args = p.parse_args()
       if args.analyze:
         # this is a parameter test
         print(f"executing {vvt.NAME} parameters {vvt.PARAM_DICT}")
      else:
         # this is the analyze test
         print(f"analyzing {vvt.NAME}")
         print(f"parameters for dh = {vvt.PARAM_dh}")
         for dh in vvt.PARAM_dh:
            xdir = f"../converge2.dh={dh}"
            print(f"xdir {xdir}")
            assert os.path.exists(xdir)

Now the parameter tests and the analyze test are contained in the same file. The arguments are queried to determine whether the ``--analyze`` option was on the command line.

It won't take much before the processing gets to be a lot of code, so it is recommended to put the parameter and analyze tests in their own functions; maybe like this:

``.pyt``:

.. code:: python

   import sys
   import nvtest
   nvtest.directives.parameterize("dh", (0.2, 0.01, 0.005))
   nvtest.directives.analyze(flag="--analyze")

   def execute():
       # this is a parameter test
       print(f"executing {vvt.NAME}: parameters {vvt.PARAM_DICT}")

   def analyze():
       # this is the analyze test
       print(f"analyzing {vvt.NAME}")
       print(f"parameters for dh = {vvt.PARAM_dh}")
       for dh in PARAM_dh:
         xdir = f"../converge2.dh={dh}"
         print(f"xdir {xdir}")
         assert os.path.exists(xdir)

   def main():
       p = argparse.ArgumentParser()
       p.add_argument("--analyze", action="store_true")
       args = p.parse_args()
       if args.analyze:
           analyze()
       else:
           execute()

   if __name__ == "__main__":
       sys.exit(main())

``.vvt``:

.. code:: python

   #VVT: parameterize : dh = 0.2 0.01 0.005
   #VVT: analyze : --analyze

   import sys
   import vvtest_util as vvt

   def execute():
       # this is a parameter test
       print(f"executing {vvt.NAME}: parameters {vvt.PARAM_DICT}")

   def analyze():
       # this is the analyze test
       print(f"analyzing {vvt.NAME}")
       print(f"parameters for dh = {vvt.PARAM_dh}")
       for dh in PARAM_dh:
         xdir = f"../converge2.dh={dh}"
         print(f"xdir {xdir}")
         assert os.path.exists(xdir)

   def main():
       p = argparse.ArgumentParser()
       p.add_argument("--analyze", action="store_true")
       args = p.parse_args()
       if args.analyze:
           analyze()
       else:
           execute()

   if __name__ == "__main__":
       sys.exit(main())
