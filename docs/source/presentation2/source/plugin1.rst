"Everything is a plugin"
------------------------

Outside of a few core classes, all functionality is provided by plugin "hooks"

.. revealjs-fragments::

  * For example, Canary does not define a test format.
  * Canary defines a plugin *specification*:

    .. code-block:: python

       @canary.hookspec
       def canary_testcase_generator() -> Type[TestCaseGenerator]: ...

  * A plugin *implementation* defines the behavior:

    .. code-block:: python

        @canary.hookspec
        def canary_testcase_generator() -> Type[TestCaseGenerator]:
            return PYTTestGenerator


.. revealjs-break::

.. code-block:: python

  class CTestTestGenerator(canary.TestCaseGenerator):

      file_patterns = ("CTestTestfile.cmake", )

      def __init__(self, file):
          # Parse the CTest file

      def lock(self, ...) -> list[canary.ResolvedTestSpec]:
          """Expand parameters, resolve fixtures

          Return list of test specs

          """
          specs: list[canary.ResolvedTestSpec] = []
          ...
          return specs


  @canary.hookspec
  def canary_testcase_generator() -> Type[TestCaseGenerator]:
      return CTestTestGenerator
