.. _extending-plugins:

Extend canary with plugins
==========================

The default behavior of ``canary`` can be modified with user defined plugins.  A plugin is a python function that is called at different phases of the ``canary`` session.  Plugin functions must be defined in a python module starting with ``canary_`` and registered with ``canary`` with the ``@canary.plugin.register`` decorator.

Plugin discovery
----------------

``canary`` loads plugin modules in the following order:

* Builtin plugins.
* Local plugins specified by the ``-p PATH`` command line option.  ``PATH`` can be a python file or directory.  If ``PATH`` is a directory, all files named ``canary_*.py`` in ``PATH`` will be loaded.
* Plugins registered through `setuptools entry points <https://docs.pytest.org/en/7.1.x/how-to/writing_plugins.html#setuptools-entry-points>`_ ``canary`` looks up the ``canary.plugin`` entrypoint to discover its plugins.  Make your plugin available by defining it in your ``pyproject.toml``:

  .. code-block:: toml

     [project.entry-points."canary.plugin"]
     plugin_name = "myproject.pluginmodule"

Writing plugins
---------------

Plugins are registered with ``canary`` by the ``canary.plugin.register`` decorator:

.. code-block:: python

    def register(*, scope: str, stage: str) -> None:
        """Register the decorated plugin function with canary"""

The possible combinations of ``scope`` and ``stage`` are:

+--------------+------------------+-------------------------------------------------------------------+
| scope        | stage            | Description                                                       |
+==============+==================+===================================================================+
|``main``      | ``setup``        | Called before argument parsing with a single argument:            |
|              |                  | ``parser: canary.Parser``.  Use this plugin to register           |
|              |                  | additional command line options with ``canary``                   |
+--------------+------------------+-------------------------------------------------------------------+
| ``session``  | ``discovery``    | Called before a session's search paths are searched for test      |
|              |                  | files.  Called with a single argument: ``session: Session``       |
|              +------------------+-------------------------------------------------------------------+
|              | ``setup``        | Called during session setup and before test case setup with a     |
|              |                  | single argument: ``session: Session``                             |
|              +------------------+-------------------------------------------------------------------+
|              | ``after_run``    | Called after session completion with a single argument:           |
|              |                  | ``session: Session``                                              |
+--------------+------------------+-------------------------------------------------------------------+
| ``test``     | ``discovery``    | Called after a test has been created but not yet setup.  Called   |
|              |                  | with a single argument: ``case: TestCase``                        |
|              +------------------+-------------------------------------------------------------------+
|              | ``setup``        | Called after a test has been setup with a single argument:        |
|              |                  | ``case: TestCase``                                                |
|              +------------------+-------------------------------------------------------------------+
|              | ``before_run``   | Called immediately before a test is run with a single argument:   |
|              |                  | ``case: TestCase``                                                |
|              +------------------+-------------------------------------------------------------------+
|              | ``after_launch`` | Called immediately after a test is launched with a single         |
|              |                  | argument: ``case: TestCase``                                      |
|              +------------------+-------------------------------------------------------------------+
|              | ``after_run``    | Called after a test has completed with a single argument:         |
|              |                  | ``case: TestCase``                                                |
+--------------+------------------+-------------------------------------------------------------------+

Alternatively, a plugin can be created by subclassing the ``canary.plugin.PluginHook`` class and overriding one or more of its methods.  The following methods are overrideable:

.. code-block:: python

    import canary

    class PluginHook:

        @staticmethod
        def main_setup(parser: "Parser") -> None:
            """Call user plugin before arguments are parsed"""

        @staticmethod
        def session_initialize(session: "Session") -> None:
            """Call user plugin during session initialization"""

        @staticmethod
        def session_discovery(finder: "Finder") -> None:
            """Call user plugin during the discovery stage, before search paths passed on the command
            line are searched

            """

        @staticmethod
        def session_finish(session: "Session") -> None:
            """Call user plugin at the end of the session"""

        @staticmethod
        def test_discovery(case: "TestCase") -> None:
            """Call user plugin during the test discovery stage"""

        @staticmethod
        def test_setup(case: "TestCase") -> None:
            """Call user plugin at the end of the test setup stage"""

        @staticmethod
        def test_before_run(case: "TestCase", *, stage: str | None = None) -> None:
            """Call user plugin immediately before running the test"""

        @staticmethod
        def test_after_launch(case: "TestCase") -> None:
            """Call user plugin immediately after the test is launched"""

        @staticmethod
        def test_after_run(case: "TestCase") -> None:
            """Call user plugin after the test has ran"""

Examples
--------

* Mask a test from running that appears in an exclude list:

  .. code-block:: python

    import canary

    @canary.plugin.register(scope="test", stage="discovery")
    def exclude_test(case: canary.TestCase):
        if case.name in EXCLUSION_DB:
            case.mask = "excluded due to ..."


* Add a flag to turn on test coverage and set the ``LLVM_PROFILE_FILE`` environment variable:

  .. code-block:: python

    import canary

    @canary.plugin.register(scope="main", stage="setup")
    def llvm_coverage_parser(parser: canary.Parser) -> None:
        parser.add_plugin_argument(
            "--code-coverage",
            action="store_true",
            default=False,
            help="Create and export coverage data",
        )

    @canary.plugin.register(scope="test", stage="setup")
    def llvm_coverage_setup(case: canary.TestCase) -> None:
        if not canary.config.get("option:code_coverage"):
            return
        if case.mask:
            return
        case.add_default_env("LLVM_PROFILE_FILE", f"{case.name}.profraw")

    @canary.plugin.register(scope="session", stage="finish")
    def llvm_coverage_combine(session: canary.Session) -> None:
        if not canary.config.get("option:code_coverage"):
            return
        files = find_raw_profiling_files(session.work_tree)
        combined_files = combine_profiling_files(files)
        create_coverage_maps(combined_files)

----------------

Alternatively, a plugin can be created by subclassing the ``canary.plugin.PluginHook`` class and overriding one or more of its methods.  For example, the plugins above can be implemented as single plugin class:

.. code-block:: python

    import canary

    class LLVMCoverage(canary.plugin.PluginHook):

        @staticmethod
        def main_setup(parser: canary.Parser) -> None:
            ...

        @staticmethod
        def session_finish(session: canary.Session) -> None:
            ...

        @staticmethod
        def test_setup(case: canary.TestCase) -> None:
            ...
