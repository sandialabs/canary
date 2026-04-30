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
     def canary_function_name() -> ReturnType:
         # some implementation

.. revealjs-break::
    :data-transition: none

When Canary needs the functionality provided by ``canary_function_name``, it calls:

.. container:: fragment

   .. code-block:: python

      response = pluginmanager.hook.canary_function_name()

.. container:: fragment

   where ``response`` is a **list** of responses, one entry for each ``canary_function_name`` hookimpl

Test case generator
^^^^^^^^^^^^^^^^^^^

.. revealjs-fragments::

   * Canary does not define a test file format, only a ``TestSpec``
   * ``TestSpec`` \ s are returned by a ``TestCaseGenerator``
   * ``TestCaseGenerator`` \ s are collected from the ``canary_testcase_generator`` hook:

     .. code-block:: python

        @canary.hookspec
        def canary_testcase_generator() -> Type[TestCaseGenerator]: ...

   * Plugins provide the ``canary_testcase_generator`` hookimpls

.. revealjs-break::
    :data-transition: none

For example

.. code-block:: python

    @canary.hookimpl
    def canary_testcase_generator() -> Type[TestCaseGenerator]:
        return PYTTestGenerator

``PYTTestGenerator`` is responsible for parsing ``.pyt`` files and creating ``TestSpec`` objects.

.. revealjs-break::
    :data-transition: none

Plugin authors can enable other formats, like CTest: [3]_

.. code-block:: python

    @canary.hookimpl
    def canary_testcase_generator() -> Type[TestCaseGenerator]:
        return CTestTestGenerator

.. [3] A CTest plugin is shipped with Canary

.. revealjs-break::
    :data-transition: none

Plugin authors can enable other formats, like CTest:

.. code-block:: python

    @canary.hookimpl
    def canary_testcase_generator() -> Type[TestCaseGenerator]:
        return CTestTestGenerator

.. code-block:: python

    class CTestTestGenerator(canary.TestCaseGenerator):

        file_patterns = ("CTestTestfile.cmake", )

        def __init__(self, file):
            self.file = file

        def lock(self, ...) -> list[canary.ResolvedTestSpec]:
            """Expand parameters, resolve fixtures.  Returns
            a list of test specs
            """
            specs: list[canary.ResolvedTestSpec] = []
            ...
            return specs

.. revealjs-break::
    :data-transition: none

Writing your own format is easy.  Suppose your tests are provided in a YAML file:

.. code-block:: yaml

    tests:
    - name: a
      script: mpiexec -n 4 my-program a.inp
      cpus: 4
    - name: b
      script: mpiexec -n 16 my-program b.inp
      cpus: 16

.. revealjs-break::
    :data-transition: none

A simple generator might be

.. code-block:: python

   class YAMLTestGenerator(canary.TestCaseGenerator):

       file_patterns = ("*.yaml", )

       def __init__(self, file):
           self.file = file

       def lock(self, ...) -> list[canary.ResolvedTestSpec]:
           specs: list[canary.ResolvedTestSpec] = []
           with open(self.file) as fh:
               entries = yaml.safe_load(fh)["tests"]
           for entry in entries:
               spec = canary.ResolvedTestSpec(
                   name=entry["name"],
                   parameters={"cpus": entry["cpus"]}
               )
               specs.append(spec)
           return specs


.. revealjs-break::
    :data-transition: none

Real world case study:

.. revealjs-fragments::

   * Sandia's Sierra Mechanics suite of codes has ~30,000 test cases
   * Test cases are defined in a derivative XML language
   * We wrote the SierraTestCaseGenerator and were able to run ~90% of tests in Canary in a matter of weeks
