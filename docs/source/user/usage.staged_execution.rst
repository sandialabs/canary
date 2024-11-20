.. _usage-staged-execution:

Defining additional execution stages
====================================

The :func:`nvtest.directives.stages` directive configures a test to run in specific stages.  All tests are assigned the stage ``run``, regardless of whether the ``stages`` directive is called.

By default ``nvtest run`` executes tests in the ``run`` stage and only a single stage is executed per invocation.  Additional stages can be run invoking ``nvtest`` as ``nvtest run --stage=STAGE ...`` **after** the initial run (with ``stage=run``).

Examples
--------

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 4-22

This test defines the additional test stage "analyze" that can be run separately from the run stage.

To determine the stage of execution, the test should parse the command line for the ``--stage`` option.  As a convenience, ``nvtest`` provides the ``make_argument_parser`` utility that creates and ``argparse.ArgumentParser`` object and adds several common arguments, including ``--stage``:

.. literalinclude:: /examples/staged/staged.pyt
    :language: python
    :lines: 24-36

The test must first be run with ``--stage=run`` (the default) to generate the test session:

.. command-output:: nvtest run -d TestResults.Staged ./staged
    :cwd: /examples
    :extraargs: -rv -w


Thereafter, the additional stages can be run:

.. command-output:: nvtest -C TestResults.Staged run --stage=analyze .
    :cwd: /examples
    :extraargs: -rv

.. note::

    ``nvtest run --stage=STAGE`` for any other stage than run should be executed in the session work tree.

.. note::

    When ``nvtest run`` is invoked with ``--stage=STAGE``, only tests having been assigned the stage ``STAGE`` will be run.

The complete file
~~~~~~~~~~~~~~~~~

.. literalinclude:: /examples/staged/staged.pyt
    :language: python

Processor counts
----------------

During any stage other than ``run``, ``nvtest`` assumes that the test uses only one processor.
