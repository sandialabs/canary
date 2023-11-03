.. _directive-keywords:

keywords
========

Mark a test with keywords.  The main use of test keywords is to filter a set of tests, such as selecting which tests to run.

.. code-block:: python

   keywords(*args, parameters=None, testname=None)

.. code-block:: python

   #VVT: keywords (parameters=..., testname=...) : args...

Parameters
----------

* ``args``: list of keywords
* ``testname``: Restrict processing of the directive to this test name
* ``parameters``: Restrict processing of the directive to certain parameter names and values

Implicit keywords
-----------------

The following implicit keywords are defined:

* The test name
* The test file basename (regardless of testname settings)
* The names of parameters, e.g.

  .. code-block::

     import nvtest
     nvtest.mark.parameterize("meshsize", (0.1, 0.01, 0.001))

  would have "meshsize" as a keyword.
* The results of running the test are added as keywords. The result strings are
   * ``notrun``: the test has not been run
   * ``notdone`` : the test is still running (or vvtest was killed while it was running)
   * ``pass`` : the test ran and completed successfully
   * ``diff`` : the test ran and completed with a numerical difference
   * ``fail`` : the test ran but crashed for some reason (exited with a non-zero exit status)
   * ``timeout`` : the test ran out of time and was killed.  A test that times out is also considered to have failed.

Examples
--------

.. code-block:: python

   import nvtest
   nvtest.mark.keywords("3D", "mhd", "circuit")

.. code-block:: python

   #VVT: keywords : 3D mhd circuit

----

.. code-block:: python

   import nvtest
   nvtest.mark.keywords("3D", "mhd", "circuit", testname="spam", parameters="np>1")

.. code-block:: python

   #VVT: keywords (testname=spam, parameters="np>1") : 3D mhd circuit
