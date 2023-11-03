How to write test files
=======================

A test file defines one or more test instances to be run by ``nvtest``. It is both a set of specifications as well as the script that executes the test.

Test specifications are also called "header directives" because they must appear at the top of the test file (the header), and they direct ``nvtest`` on how to run the test. Consider a file called ``atest.vvt`` having this content:

.. code-block:: python

    import nvtest
    nvtest.mark.parameterize("np", (1, 4))
    nvtest.mark.keywords("unit", "fracture", "2D")
    nvtest.mark.link("input.yml")
    nvtest.mark.enable(platforms="not ATS*")

    def test():
        self = nvtest.test.instance
        mpiexec = nvtest.Executable("mpiexec")
        mpiexec("-n", self.parameters.np, "myapp", "input.yml")
        if mpiexec.returncode != 0:
            raise nvtest.TestFailedError("myapp failed!")

This test file would expand into two test instances, one with the parameter ``np=1`` and one with ``np=4``. The test scripting uses the parameter values to adjust what it actually executes (in this case, it runs a serial version of the application or an MPI parallel version).

The keywords are arbitrary and allow the test to be selected using keyword filtering (using the ``-k`` command line option). The "enable" directive tells ``nvtest`` to only run the test on platforms whose name does not start with "ATS".

Every test will have the file ``vvtest_util.py`` written to the execution directory, and is used to access the test parameters and other test-specific and runtime-specific information.

Thus, writing a test consists of deciding what information to provide to ``nvtest`` prior to execution via the header directives, and writing the scripting to execute the test (most likely using the ``vvtest_util.py`` for information).
