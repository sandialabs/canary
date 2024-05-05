.. _nvtest-testfile:

The test file
=============

A test file is a python script ending with ``.pyt``.  A good test ensures the correctness of output given a set of inputs and should be as simple and fast running as possible.

.. note::

    ``nvtest`` also runs ``vvtest`` ``.vvt`` test files and while ``vvtest`` allows for its test files to be written in any language, ``nvtest`` assumes the files are python.

Test file structure
-------------------

The test file is composed of two parts:

.. image:: /file.png
    :width: 800

Directives
~~~~~~~~~~

These lines provide instructions to ``nvtest`` regarding the setup and cleanup of the test.  These instructions are provided through the ``nvtest.directives`` namespace.  For example,

.. code-block:: python

    import nvtest
    nvtest.directives.copy("file.txt")

would copy ``file.txt`` from the test's source directory into the the test's execution directory.

See :ref:`test-directives` for more.

Body
~~~~

Executable statements that are run during the session's run phase.

Best practices
~~~~~~~~~~~~~~

Because [``.pyt``] test files are imported during the discovery process, the
test body should be contained in one or more functions with an entry point
guarded by

.. code-block:: python

    if __name__ == "__main__":
        # run the test

Test case expansion
-------------------

Test files define one or more *test cases*.  In the simplest case, a test file defines a single test case whose name is the basename of the test file.  In more complex cases, a single test file defines parameters that expand to define multiple test cases whose names are a combination of the basename of the test file and parameter/name pairs.  For example:

.. code-block:: python

    import nvtest
    nvtest.directives.parameterize("np", (1, 4))

would expand into two test instances, one with the parameter ``np=1`` and one with ``np=4``.  Each test case would execute in its own directory and the test script should query for the value of ``np`` and adjust the test accordingly.  Test parameters and other test-specific and runtime-specific information are accessed from the ``nvtest.test.instance`` object:

.. code-block:: python

    import nvtest
    nvtest.directives.parameterize("np", (1, 4))
    def test():
        self = nvtest.test.instance
        print(self.parameters.np)

A complete example
------------------

.. code-block:: python

    import nvtest
    nvtest.directives.parameterize("np", (1, 4))
    nvtest.directives.keywords("unit", "fracture", "2D")
    nvtest.directives.link("input.yml")

    def test():
        self = nvtest.test.instance
        mpiexec = nvtest.Executable("mpiexec")
        mpiexec("-n", self.parameters.np, "myapp", "input.yml")
        if mpiexec.returncode != 0:
            raise nvtest.TestFailedError("myapp failed!")

This test file would expand into two test instances, one with the parameter ``np=1`` and one with ``np=4``. The test scripting uses the parameter values to adjust what it actually executes (in this case, it runs a serial version of the application or an MPI parallel version).

The keywords are arbitrary and allow the test to be selected using keyword filtering (using the ``-k`` command line option).
