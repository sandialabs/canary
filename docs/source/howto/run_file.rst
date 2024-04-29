.. _howto-run-file:

How to run specific tests from a file
=====================================

Select tests can be executed by specifying their paths in a ``json`` or ``yaml`` configuration file with the following layout:

.. code-block:: yaml

    testpaths:
    - root: <root>
      paths:
      - <path_1>
      - <path_2>
      ...
      - <path_n>

where ``<root>`` is a parent directory of the tests and ``<path_i>`` are the file paths relative to ``<root>``.  If ``<root>`` is a relative path, it is considered relative to the path of the configuration file.  Consider, for example, the examples directory tree:

.. command-output:: nvtest tree --exclude-results .
    :cwd: /examples

To run only ``centered_space/test.pyt`` and ``parameterize/test2.pyt``, write the following to ``tests.json``

.. literalinclude:: /examples/tests.json
    :language: json

and pass it to ``nvtest run``:

.. command-output:: nvtest run tests.json
    :cwd: /examples
