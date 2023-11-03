How to find and list test files
===============================

``nvtest find`` finds tests in a search path and prints basic information about each test:

Basic usage
-----------

.. code-block:: console

   $ nvtest find PATH
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   rootdir: PATH
   collected 1392 tests from 490 files
   running 1264 test cases from 435 files with 10 workers
   skipping 128 test cases
     • 69 deselected due to platform expression ceelan evaluated to False
     • 29 deselected due to platform expression null evaluated to False
     • 19 deselected due to exceeding cpu count of machine
     • 6 deselected because it contained the TDD keyword
     • 4 deselected due to platform expression not Darwin evaluated to False
     • 1 deselected due to disabled
   —— PATH ———————————————————————
     01:00:00    irr_unistretch.np=1
     01:00:00    irr_unistretch.np=2
     00:02:30    je_test.np=1
     ...
     01:00:00    GMG_eos_path.PATHID=12.PATHNAME=hsc_cycle.np=1
     01:00:00    MG_eos_path.PATHID=4.PATHNAME=hsc.np=1

   found 1264 test cases

Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``fast`` keyword:

.. code-block:: console

   $ nvtest find -k fast PATH
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   rootdir: PATH
   collected 1392 tests from 490 files
   running 853 test cases from 275 files with 10 workers
   skipping 539 test cases
     • 418 deselected by keyword expression
     • 69 deselected due to platform expression ceelan evaluated to False
     • 29 deselected due to platform expression null evaluated to False
     • 9 deselected due to skipped dependencies
     • 5 deselected due to exceeding cpu count of machine
     • 4 deselected due to platform expression not Darwin evaluated to False
     • 4 deselected because it contained the TDD keyword
     • 1 deselected due to disabled
   —— PATH ———————————————————————
     00:02:30    je_test.np=1
     00:02:30    je_test.np=2
     00:02:30    je_test.np=3
     ...
     00:02:30    MG_eos_porosity_path.PATHID=4.PATHNAME=hsc.np=1
     00:02:30    MG_eos_porosity_path.PATHID=12.PATHNAME=hsc_cycle.np=1

   found 853 test cases

Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies.  Eg, to print a DAG of tests with the ``fast`` keyword:

.. code-block:: console

   $ nvtest find -g -k fast PATH
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   rootdir: PATH
   collected 1392 tests from 490 files
   running 853 test cases from 275 files with 10 workers
   skipping 539 test cases
     • 418 deselected by keyword expression
     • 69 deselected due to platform expression ceelan evaluated to False
     • 29 deselected due to platform expression null evaluated to False
     • 9 deselected due to skipped dependencies
     • 5 deselected due to exceeding cpu count of machine
     • 4 deselected due to platform expression not Darwin evaluated to False
     • 4 deselected because it contained the TDD keyword
     • 1 deselected due to disabled
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
   platform Darwin -- Python 3.10.8, num cores: 10, max cores: 10
   rootdir: PATH
   collected 1392 tests from 490 files
   running 1264 test cases from 435 files with 10 workers
   skipping 128 test cases
     • 69 deselected due to platform expression ceelan evaluated to False
     • 29 deselected due to platform expression null evaluated to False
     • 19 deselected due to exceeding cpu count of machine
     • 6 deselected because it contained the TDD keyword
     • 4 deselected due to platform expression not Darwin evaluated to False
     • 1 deselected due to disabled
   —— PATH —————————————————————————
  2D                 fmhd                       neo_hookean
  3D                 fortran                    nodistribution
  ...
  ferom_csd          mrdynamics                 vumat
  ferom_nlk          msdsf                      xfem
  ferroceramic       mulliken_boyce             xflagrangian
