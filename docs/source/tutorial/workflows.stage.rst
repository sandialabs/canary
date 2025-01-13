.. _tutorial-workflows-staged:

Staged workflows
================

In ``nvtest``, tests are organized into execution stages to facilitate structured testing and evaluation. Each test defines a ``run`` stage, which is the stage that is executed on the first invocation of ``nvtest run``. Additional stages can be defined and run by passing the ``--stage=STAGE`` option to ``nvtest run``.

Consider the following example:

.. literalinclude:: /examples/staged/staged.pyt
    :language: python

In this example, an expensive ``run`` stage is defined as well as a relatively inexpensive ``analyze`` and ``plot`` stages for the case that ``cpus=1``.  The ``run`` stage is executed when ``nvtest run`` is invoked for the first time:

.. note::

    The ``run`` stage is always defined for each test, whether explicitly or implicitly, as in this example.

.. command-output:: nvtest -C run ./staged
    :cwd: /examples
    :nocache:
    :extraargs: -w


after the first exectuion, the additional stages can be run:

.. command-output:: nvtest -C TestResults run --stage=analyze
    :cwd: /examples
    :nocache:

.. command-output:: nvtest -C TestResults run --stage=plot
    :cwd: /examples
    :nocache:
