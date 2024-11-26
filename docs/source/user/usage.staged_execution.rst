.. _usage-staged-execution:

Defining additional execution stages
====================================

All tests are configured to run during the ``run`` stage of execution.  :func:`nvtest.directives.stages` configures a test to run in additional stages of execution, as illustrated in the following example.

Example
--------

The following example defines the additional post processing stages "analyze" and "plot", each defining their behavior in a corresponding function:

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 4-7

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 10-11

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 18-19

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 27-28

To determine the stage of execution, the test should parse the command line for the ``--stage`` option.  As a convenience, ``nvtest`` provides the ``make_argument_parser`` utility that creates and ``argparse.ArgumentParser`` object and adds several common arguments, including ``--stage``:

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 38-50

The test must first be run with ``--stage=run`` (the default) to generate the test session:

.. note::

    All tests are assigned the stage ``run``, regardless of whether the ``stages`` directive is called.

.. command-output:: nvtest run -d TestResults.Staged ./staged
    :cwd: /examples
    :extraargs: -rv -w

Thereafter, the additional stages can be run:

.. note::

    When ``nvtest run`` is invoked with ``--stage=STAGE``, only tests having been assigned the stage ``STAGE`` will be run.

.. note::

    ``nvtest run --stage=STAGE`` for any other stage than run should be executed in the session work tree.

.. command-output:: nvtest -C TestResults.Staged run --stage=analyze .
    :cwd: /examples
    :extraargs: -rv

.. command-output:: nvtest -C TestResults.Staged run --stage=plot .
    :cwd: /examples
    :extraargs: -rv

.. admonition:: Processor counts

    During any stageanalyze other than ``run``, ``nvtest`` assumes that the stage will use only one processor.

The complete file
.................

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
