"""
How to find and list test files
===============================

``nvtest find`` finds tests in a search path and prints basic information about each test:

Basic usage
-----------

.. code-block:: console

   nvtest find PATH

Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``fast`` keyword:

.. code-block:: console

   nvtest find -k fast PATH

The ``-k`` option can take a python expression, eg

.. code-block:: console

   nvtest find -k 'fast and regression' PATH

Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies.  Eg, to print a DAG of tests with the ``fast`` keyword:

.. code-block:: console

   $ nvtest find -g -k fast PATH
   ...
   ├── je_test[np=1]
   ├── je_test[np=2]
   ...
   └── sphere
   │   ├── sphere[np=1,subdivisions=1]
   │   ├── sphere[np=1,subdivisions=2]
   │   ├── sphere[np=1,subdivisions=3]
   │   ├── sphere[np=1,subdivisions=4]
   │   └── sphere[np=1,subdivisions=5]

Show available keywords
-----------------------

.. code-block:: console

   $ nvtest find --keywords PATH
   ...
   —— PATH —————————————————————————
  2D                 fmhd                       neo_hookean
  3D                 fortran                    nodistribution
  ...
  ferom_csd          mrdynamics                 vumat
  ferom_nlk          msdsf                      xfem
  ferroceramic       mulliken_boyce             xflagrangian

"""


def test_finding():
    pass
