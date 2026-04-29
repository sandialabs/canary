"Everything is a plugin"
------------------------

Outside of a few core classes, all functionality is provided by plugin "hooks"

.. revealjs-fragments::

    **Including test file formats**

.. revealjs-break::
    :data-transition: none

Canary defines a plugin *specification*:

.. code-block:: python

   @canary.hookspec
   def canary_function_name() -> ReturnType: ...

.. container:: fragment

  And plugin authors provide the *implementation*:

  .. code-block:: python

     @canary.hookimpl
     def canary_function_name() -> ReturnType: ...


.. revealjs-break::
    :data-transition: none

For example, test cases:

.. code-block:: python

    @canary.hookspec
    def canary_testcase_generator() -> Type[TestCaseGenerator]:
        return PYTTestGenerator

.. container:: fragment

    Which allows reading tests from many sources, including CTest:

    .. code-block:: python

        @canary.hookspec
        def canary_testcase_generator() -> Type[TestCaseGenerator]:
            return CTestTestGenerator

.. revealjs-break::
    :data-transition: none

.. code-block:: python

    class CTestTestGenerator(canary.TestCaseGenerator):

        file_patterns = ("CTestTestfile.cmake", )

        def __init__(self, file):
            # Parse the CTest file

        def lock(self, ...) -> list[canary.ResolvedTestSpec]:
            """Expand parameters, resolve fixtures.  Returns
            a list of test specs
            """
            specs: list[canary.ResolvedTestSpec] = []
            ...
            return specs
