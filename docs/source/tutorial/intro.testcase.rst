What is a test case?
====================

A test case

* is an instance of :class:`~_canary.test.case.TestCase`;
* is generated from an implementation of :class:`~_canary.generator.AbstractTestGenerator`; and
* is the concrete realization of the test files's body, executed with specific values for each parameter.

Example
-------

.. code-block:: python
    :emphasize-lines: 6-10

    import sys
    import canary
    canary.directives.keywords("spam")
    canary.directives.parameters("breakfast", ("bacon", "eggs"))

    def test() -> int:
        instance = canary.get_instance()
        assert "spam" in instance.keywords
        assert instance.parameters.breakfast in ("bacon", "eggs")
        return 0


    if __name__ == "__main__":
        sys.exit(test())


.. note::

   :class:`~_canary.test.instance.TestInstance` is a read-only mirror of the :class:`~_canary.test.case.TestCase`, made available by :func:`canary.get_instance`.  The test instance contains all relevant information about the test case being executed.
