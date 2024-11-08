.. _howto-plugins:

Extend nvtest with plugins
==========================

**Reference**: :ref:`extending-plugins` for more information on plugins.

Examples
--------

* Mask a test from running that appears in an exclude list:

  .. code-block:: python

    import nvtest

    @nvtest.plugin.register(scope="test", stage="discovery")
    def exclude_test(case: nvtest.TestCase):
        if case.name in EXCLUSION_DB:
            case.mask = "excluded due to ..."


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
        if case.mask:
            return
        case.add_default_env("LLVM_PROFILE_FILE", f"{case.name}.profraw")

    @nvtest.plugin.register(scope="session", stage="finish")
    def llvm_coverage_combine(session: nvtest.Session) -> None:
        if not nvtest.config.get("option:code_coverage"):
            return
        files = find_raw_profiling_files(session.root)
        combined_files = combine_profiling_files(files)
        create_coverage_maps(combined_files)

----------------

Alternatively, a plugin can be created by subclassing the ``nvtest.plugin.PluginHook`` class and overriding one or more of its methods.  For example, the plugins above can be implemented as single plugin class:

.. code-block:: python

    import nvtest

    class LLVMCoverage(nvtest.plugin.PluginHook):

        @staticmethod
        def main_setup(parser: nvtest.Parser) -> None:
            ...

        @staticmethod
        def session_finish(session: nvtest.Session) -> None:
            ...

        @staticmethod
        def test_setup(case: nvtest.TestCase) -> None:
            ...
