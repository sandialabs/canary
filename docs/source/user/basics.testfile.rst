.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-testfile:

The test file
=============

A test file is a python script ending with ``.pyt``.  If execution of the script results in an exit code of ``0``, the test passes.  Non-zero exit codes indicate some other type of test failure (see :ref:`basics-status` for additional test statuses).  A good test ensures the correctness of output given a set of inputs and should be as simple, and fast running, as possible.

.. note::

    ``canary`` also runs ``vvtest`` ``.vvt`` test files with the restriction that ``canary`` assumes that the files are written in Python (``vvtest`` allows for its test files to be written in any language).

Test file structure
-------------------

The test file is composed of two parts: :ref:`directives<file-directives>` and the :ref:`body<file-body>`, each described below.

.. _file-directives:

Directives
~~~~~~~~~~

These lines provide instructions to ``canary`` regarding the setup and cleanup of the test.  These instructions are provided through the ``canary.directives`` namespace.  For example,

.. code-block:: python

    import canary
    canary.directives.copy("file.txt")

would copy ``file.txt`` from the test's source directory into the the test's execution directory.

See :ref:`test-directives` for more.

.. _file-body:

Body
~~~~

Executable statements that are run during the session's run phase, for example:

.. code-block:: python

    def test():
        assert 2 + 2 == 4

Best practices
~~~~~~~~~~~~~~

Because ``.pyt`` test files are imported during the discovery process, the test body should be contained in one or more functions with an entry point guarded by

.. code-block:: python

    if __name__ == "__main__":
        # run the test

Test case expansion
-------------------

Test files define one or more :ref:`test cases <basics-testcase>`.  In the simplest case, a test file defines a single test case whose name is the basename of the test file.  In more complex cases, a single test file defines parameters that expand to define multiple test cases whose names are a combination of the basename of the test file and parameter/name pairs.  For example:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 4-6

would expand into two test instances, one with the parameter ``a=1`` and one with ``a=4`` as shown.

.. image:: /dot/TestFile1.png
    :align: center

Each test case would execute in its own directory and the test script should query for the value of ``a`` and adjust the test accordingly.  Test parameters and other test-specific and runtime-specific information are accessed from the ``canary.test.instance`` object which is accessible via ``canary.get_instance()``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 8-10

More generally, test files can define an arbitrary number of cases:

.. image:: /dot/TestFile.png
    :align: center

A complete example
------------------

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python

This test file would expand into two test instances, one with the parameter ``a=1`` and one with ``a=4``, as seen with the ``canary describe`` command:

.. command-output:: canary describe parameterize/parameterize1.pyt
    :cwd: /examples
