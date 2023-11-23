The test file
=============

A test file is an executable script with ``.pyt`` or ``.vvt``.  A good test ensures the correctness of output given a set of inputs and should be as simple and fast running as possible.

The test file is composed of two parts:

.. rubric:: 1. Directives

These lines provide instructions to ``nvtest`` regarding the setup and cleanup of the test.  For ``.pyt`` files, these instructions are provided through the ``nvtest.mark`` namespace:

.. code-block:: python

    import nvtest
    nvtest.mark.copy("file.txt")

For ``.vvt`` files, directives are lines starting with ``#VVT`` and appear at the top of the test file, eg:

.. code-block:: python

    #VVT: copy : file.txt

See :ref:`test-directives` for more.

.. rubric:: 2. Body

Executable statements that are run during the session's run phase.

Test case expansion
-------------------

Test files define one or more *test cases*.  In the simplest case, a test file defines a single test case whose name is the basename of the test file.  In more complex cases, a single test file defines parameters that expand to define multiple test cases whose names are a combination of the basename of the test file and parameter/name pairs.  For example:

``.pyt``:

.. code-block:: python

    import nvtest
    nvtest.mark.parameterize("np", (1, 4))

``.vvt``:

.. code-block:: python

    #VVT: parameterize : np = 1 4

would expand into two test instances, one with the parameter ``np=1`` and one with ``np=4``.  Each test case would execute in its own directory and the test script should query for the value of ``np`` and adjust the test accordingly.  Test parameters and other test-specific and runtime-specific information are accessed differently depending on the test file type.  For ``.pyt`` files, import and use the ``nvtest.test.instance`` and for ``.vvt`` files, import ``vvtest_util``.

``.pyt``:

.. code-block:: python

    import nvtest
    nvtest.mark.parameterize("np", (1, 4))
    def test():
        self = nvtest.test.instance
        print(self.parameters.np)

``.vvt``:

.. code-block:: python

    #VVT: parameterize : np = 1 4
    import vvtest_util as vvt
    def test():
        print(vvt.np)

A complete example
------------------

``.pyt``:

.. code-block:: python

    import nvtest
    nvtest.mark.parameterize("np", (1, 4))
    nvtest.mark.keywords("unit", "fracture", "2D")
    nvtest.mark.link("input.yml")

    def test():
        self = nvtest.test.instance
        mpiexec = nvtest.Executable("mpiexec")
        mpiexec("-n", self.parameters.np, "myapp", "input.yml")
        if mpiexec.returncode != 0:
            raise nvtest.TestFailedError("myapp failed!")

``.vvt``:

.. code-block:: python

    #VVT: parameterize : np = 1 4
    #VVT: keywords : unit fracture 2D
    #VVT: link input.yml
    import nvtest
    import vvtest_util as vvt

    def test():
        mpiexec = nvtest.Executable("mpiexec")
        mpiexec("-n", vvt.np, "myapp", "input.yml")
        if mpiexec.returncode != 0:
            raise nvtest.TestFailedError("myapp failed!")

This test file would expand into two test instances, one with the parameter ``np=1`` and one with ``np=4``. The test scripting uses the parameter values to adjust what it actually executes (in this case, it runs a serial version of the application or an MPI parallel version).

The keywords are arbitrary and allow the test to be selected using keyword filtering (using the ``-k`` command line option).
