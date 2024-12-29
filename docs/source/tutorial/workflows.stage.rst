.. _tutorial-workflows-staged:

Staged workflows
================

In ``nvtest``, tests are organized into execution stages to facilitate structured testing and evaluation. Each test defines a ``run`` stage, which is the stage that is executed on the first invocation of ``nvtest run``. Additional stages can be defined and run by passing the ``--stage=STAGE`` option to ``nvtest run``.

Consider the following example:


.. code-block:: python

    import sys
    import nvtest
    nvtest.directives.stages("run", "post")


    def run() -> int:
        # a relatively expensive execution
        ...


    def post() -> int:
        # a relatively inexpensive post processing routine that may run many times after a sing run
        ...


    def main() -> int:
        p = nvtest.make_argument_parser()
        args = p.parse_args()
        if args.stage == "run":
            return run()
        elif args.stage == "post":
            return post()


    if __name__ == "__main__":
        sys.exit(main())


In this example, a relatively expensive ``run`` stage is defined as well as a relatively inexpensive ``post`` stage.  The ``run`` stage is executed when ``nvtest run`` is invoked for the first time:

.. code-block:: console

    nvtest run ...


after the first exectuion, the additional stages can be run:

.. code-block:: console

    nvtest -C TestResults run --stage=post ...


.. note::

    The ``run`` stage is always defined for each test, whether implicitly or explicitly as in this example.
