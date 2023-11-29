Getting started
===============

Install nvtest
--------------

``nvtest`` requires Python 3.9+

1. Create and activate a python virtual environment or conda environment.  For instructions on creating a conda environment, see :ref:`conda-env`.

2. Clone and install via ``pip``

   .. code-block:: console

      git clone git@cee-gitlab.gov:tfuller/nvtest
      cd nvtest
      pip install -e .

  .. note::

    The ``-e`` flag puts the installation in "editable" mode, allowing changes to the source code to appear in your python environment.

3. Check the installation

  .. code-block:: console

     $ nvtest --version
     nvtest 0.1


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

In this second, somewhat contrived, test, the external program "``my-add``" adds two numbers and writes the result to the console's stdout.  The test executes the script, reads it output, and verifies correctness.

.. code:: python

   #!/usr/bin/env python3
   # contents of my-add
   import argparse
   import sys

   def add(a: int, b: int) -> int:
       return a + b

   def main():
       p = argparse.ArgumentParser(description="Add two numbers a and b")
       p.add_argument("a", type=int)
       p.add_argument("b", type=int)
       args = p.parse_args()
       print(add(args.a, args.b))
       return 0


   if __name__ == "__main__":
       sys.exit(main())


.. code:: python

   # contents of test_my_add.pyt
   import sys
   import nvtest

   def test() -> int:
       my_add = nvtest.Executable("./my-add")
       out = my_add("3", "2", output=str)
       assert exe.returncode == 0
       assert int(out.strip()) == 5
       return 0

   if __name__ == "__main__":
       sys.exit(test())

To execute it, navigate to the folder containing the script and test file and execute:

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
   STARTING: test_my_add
   FINISHED: test_my_add PASS
   ================================== 1 pass in 0.14s. =================================

Getting help
------------

``nvtest`` has several subcommands.  To get the list of subcommands, issue

.. code-block:: console

   nvtest -h

To get help on an individual subcommand, issue

.. code-block:: console

   nvtest SUBCOMMAND -h


.. _conda-env:

How to set up a conda environment
---------------------------------

The following conda environment is a good starting point for scientific computing.  Write the following to ``environment.yml``

.. code-block:: yaml

   name:
   dependencies:
   - python=3.9
   - numpy
   - matplotlib
   - scipy
   - netcdf4
   - imageio
   - yaml
   - pyyaml
   - requests
   - six
   - urllib3
   - pytest
   - coverage
   - sphinx
   - alabaster
   - black
   - flake8
   - bokeh
   - conda-forge::conda-pack
   - conda-forge::clingo

At the command line, execute the following, substituting ``PREFIX`` for the prefix of your choice:

.. code-block:: console

  $ export PREFIX=YOUR_PREFIX
  $ mkdir -p $PREFIX/python
  $ cd $PREFIX/python
  $ # Write environment.yml
  $ conda env create -k -f ./environment.yml -p ./3.9

This will put a full-featured python environment in ``PREFIX/python/3.9``.

