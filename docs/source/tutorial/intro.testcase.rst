What is a test case?
====================

A test case

* is an instance of :class:`~_nvtest.test.case.TestCase`;
* is generated from an implementation of :class:`~_nvtest.generator.AbstractTestGenerator`; and
* is the concrete realization of the test files's body, executed with specific values for each parameter.

Example
-------

.. code-block:: python
    :emphasize-lines: 6-10

    import sys
    import nvtest
    nvtest.directives.keywords("spam")
    nvtest.directives.parameters("breakfast", ("bacon", "eggs"))

    def test() -> int:
        instance = nvtest.get_instance()
        assert "spam" in instance.keywords
        assert instance.parameters.breakfast in ("bacon", "eggs")
        return 0


    if __name__ == "__main__":
        sys.exit(test())


.. note::

   :class:`~_nvtest.test.instance.TestInstance` is a read-only mirror of the :class:`~_nvtest.test.case.TestCase`, made available by :func:`nvtest.get_instance`.  The test instance contains all relevant information about the test case being executed.
