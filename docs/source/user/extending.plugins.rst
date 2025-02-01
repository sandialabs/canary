.. _extending-plugins:

Extend canary with plugins
==========================

The default behavior of ``canary`` can be modified with user defined plugins.  A plugin is a python function that is called at different phases of the ``canary`` session.  Plugins are loaded and managed by `pluggy <https://pluggy.readthedocs.io/en/stable/>`_.

Plugin discovery
----------------

``canary`` loads plugin modules in the following order:

* Builtin plugins.
* Plugins registered through `setuptools entry points <https://docs.pytest.org/en/7.1.x/how-to/writing_plugins.html#setuptools-entry-points>`_ ``canary`` looks up the ``canary`` entrypoint to discover its plugins.  Make your plugin available by defining it in your ``pyproject.toml``:

  .. code-block:: toml

     [project.entry-points.canary]
     plugin_name = "myproject.pluginmodule"

* Local plugins specified by the ``-p PATH`` command line option.  ``PATH`` can be a python file or directory.  If ``PATH`` is a directory, all files named ``canary_*.py`` in ``PATH`` will be loaded.

Writing plugins
---------------

Plugin functions are registered with ``canary`` by decorating with ``canary.hookimpl`` decorator:

.. code-block:: python

    @canary.hookimpl
    def canary_plugin_name(...):
       ...

Recognized plugin hooks are:

+----------------------------------------------------+-------------------------------------------------------------------------------------+
| hook                                               | Description                                                                         |
+====================================================+=====================================================================================+
|``canary_addoption(parser: canary.Parser)``         | Use this plugin to register  additional command line options with ``canary``        |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_configure(config: canary.Config)``         | Called after parsing arguments.  Use this plugin to modify the Canary configuration |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_session_start(session: canary.Session)``   | Called after session initialization and before test discovery                       |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_session_finish(session: canary.Session)``  | Called after the session finished                                                   |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_testcase_generator()``                     | Returns an implementation of :class:`~_canary.generator.AbstractTestGenerator`      |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_testcase_modify(case: canary.TestCase)``   | Called after test cases have been masked by filtering criteria                      |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_testcase_setup(case: canary.TestCase)``    | Called after the test case's working directory is setup                             |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_testcase_finish(case: canary.TestCase)``   | Called after the test case is run                                                   |
+----------------------------------------------------+-------------------------------------------------------------------------------------+
|``canary_session_report()``                         | Called by the ``canary report`` subcommand                                          |
+----------------------------------------------------+-------------------------------------------------------------------------------------+


Examples
--------

* Mask a test from running that appears in an exclude list:

  .. code-block:: python

    import canary

    @canary.hookimpl
    def canary_testcase_modify(case: canary.TestCase):
        if case.name in EXCLUSION_DB:
            case.mask = "excluded due to ..."


* Add a flag to turn on test coverage and set the ``LLVM_PROFILE_FILE`` environment variable:

  .. code-block:: python

    import canary

    @canary.hookimpl
    def canary_addoption(parser: canary.Parser) -> None:
        parser.add_plugin_argument(
            "--code-coverage",
            action="store_true",
            default=False,
            help="Create and export coverage data",
        )

    @canary.hookimpl
    def canary_testcase_modify(case: canary.TestCase) -> None:
        if not canary.config.get("option:code_coverage"):
            return
        if case.mask:
            return
        case.add_default_env("LLVM_PROFILE_FILE", f"{case.name}.profraw")

    @canary.hookimpl
    def canary_session_finish(session: canary.Session) -> None:
        if not canary.config.get("option:code_coverage"):
            return
        files = find_raw_profiling_files(session.work_tree)
        combined_files = combine_profiling_files(files)
        create_coverage_maps(combined_files)
