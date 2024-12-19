.. _tutorial-intro-pyt:

What is a pyt test file?
========================

Files ending in ``.pyt`` are ``nvtest``'s "native" test file format.  ``pyt`` files are python files consisting of two parts:

* ``nvtest`` :ref:`directives <test-directives>`; and
* the test body

nvtest directives
-----------------

:ref:`Test directives <test-directives>` are python function calls that communicate information to
the test generator about the test file.  For example, the :ref:`keywords <directive-keywords>`
directive assigns keywords (labels) to the test which can be used in filtering operations:

.. code-block:: python

    import nvtest
    nvtest.directives.keywords("spam")

Directives are evaluated when the test file is imported and must appear at the file's global scope
and not in function or class scopes.

Test body
---------

The test body verifies particular functionalities to ensure they align with the specified requirements. Since test files are imported to assess their directives, the test body should be encapsulated within a function and executed only when the file is run, as in the following example:

.. code-block:: python
    :emphasize-lines: 3-5

    import sys

    def test() -> int:
        # Check specific functionalities
        return 0


    if __name__ == "__main__":
        sys.exit(test())

A test exiting with code ``0`` is considered successful.  Otherwise, a failure :ref:`status <basics-status>` is assigned, depending on the exit code.
