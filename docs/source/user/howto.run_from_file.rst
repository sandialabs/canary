.. _howto-run-file:

Run specific test files
=======================

Run a file directly
-------------------

Test files can be run directly by passing their paths to ``nvtest run``

.. command-output:: nvtest run ./basic/first.pyt
    :nocache:
    :extraargs: -w -rv
    :cwd: /examples
    :setup: rm -rf TestResults

.. command-output:: ls -F TestResults
    :nocache:
    :cwd: /examples

If a path separator is replaced with a colon ``:``, the path is interpreted as ``root:path``.  ie, path segments after the ``:`` are used as the relative path to the test execution directory:

.. command-output:: nvtest run .:basic/first.pyt
    :nocache:
    :cwd: /examples
    :extraargs: -w -rv
    :setup: rm -rf TestResults

.. command-output:: ls -F TestResults
    :nocache:
    :cwd: /examples

Running tests from a file
-------------------------

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

To run only ``centered_space/centered_space.pyt`` and ``parameterize/parameterize2.pyt``, write the following to ``tests.json``

.. literalinclude:: /examples/tests.json
    :language: json

and pass it to ``nvtest run``:

.. command-output:: nvtest run -f tests.json
    :cwd: /examples
    :extraargs: -rv -w
    :setup: rm -rf TestResults
