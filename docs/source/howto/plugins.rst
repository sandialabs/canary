.. _howto-plugins:

Extend nvtest with plugins
==========================

The default behavior of ``nvtest`` can be modified with user defined plugins.  A plugin is a python function that is called at different phases of the ``nvtest`` session.  Plugin functions must be defined in a python module starting with ``nvtest_`` and registered with ``nvtest`` with the ``@nvtest.plugin.register`` decorator.

Plugin discovery
----------------

``nvtest`` loads plugin modules in the following order:

* builtin plugins;
* plugins specified by the ``-p PATH`` command line option; and
* plugins registered through `setuptools entry points <https://docs.pytest.org/en/7.1.x/how-to/writing_plugins.html#setuptools-entry-points>`_

Writing plugins
---------------

Plugins are registered with ``nvtest`` by the ``nvtest.plugin.register`` decorator:

.. code-block:: python

    def register(*, scope: str, stage: str) -> None:
        """Register the decorated plugin function with nvtest"""

The possible combinations of ``scope`` and ``stage`` are:

+--------------+---------------+-------------------------------------------------------------------+
| scope        | stage         | Description                                                       |
+==============+===============+===================================================================+
|``main``      | ``setup``     | Called before argument parsing with a single argument:            |
|              |               | ``parser: nvtest.Parser``.  Use this plugin to register           |
|              |               | additional command line options with ``nvtest``                   |
+--------------+---------------+-------------------------------------------------------------------+
| ``session``  | ``discovery`` | Called before a session's search paths are searched for test      |
|              |               | files.  Called with a single argument: ``session: Session``       |
|              +---------------+-------------------------------------------------------------------+
|              | ``setup``     | Called during session setup and before test case setup with a     |
|              |               | single argument: ``session: Session``                             |
|              +---------------+-------------------------------------------------------------------+
|              | ``finish``    | Called after session completion with a single argument:           |
|              |               | ``session: Session``                                              |
+--------------+---------------+-------------------------------------------------------------------+
| ``test``     | ``discovery`` | Called after a test has been created but not yet setup.  Called   |
|              |               | with a single argument: ``case: TestCase``                        |
|              +---------------+-------------------------------------------------------------------+
|              | ``setup``     | Called after a test has been setup with a single argument:        |
|              |               | ``case: TestCase``                                                |
|              +---------------+-------------------------------------------------------------------+
|              | ``finish``    | Called after a test has completed with a single argument:         |
|              |               | ``case: TestCase``                                                |
+--------------+---------------+-------------------------------------------------------------------+

Examples
--------

* Mask a test from running that appears in an exclude list:

  .. code-block:: python

    import nvtest

    @nvtest.plugin.register(scope="test", stage="discovery")
    def exclude_test(case: nvtest.TestCase):
        if case.name in EXCLUSION_DB:
            case.status.set("masked", "excluded due to ...")


* Add a flag to turn on test coverage and set the ``LLVM_PROFILE_FILE`` environment variable:

  .. code-block:: python

    import nvtest

    @nvtest.plugin.register(scope="main", stage="setup")
    def llvm_coverage_parser(parser: nvtest.Parser) -> None:
        parser.add_plugin_argument(
            "--code-coverage",
            action="store_true",
            default=False,
            help="Create and export coverage data",
        )

    @nvtest.plugin.register(scope="test", stage="setup")
    def llvm_coverage_setup(case: nvtest.TestCase) -> None:
        if not nvtest.config.get("option:code_coverage"):
            return
        if case.masked:
            return
        case.add_default_env("LLVM_PROFILE_FILE", f"{case.name}.profraw")
