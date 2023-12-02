.. _directive-enable:

enable
======

Explicitly mark a test to be enabled (or not)

.. code-block:: python

   nvtest.directives.enable(arg, options=None, platforms=None, testname=None)

.. code-block:: python

   #VVT: enable (options=..., platforms=..., testname=...) : arg

Parameters
----------
* ``arg``: If ``True``, enable the test.  If ``False``, disable the test
* ``testname``: Restrict processing of the directive to this test name
* ``platforms``: Restrict processing of the directive to certain platform or platforms
* ``options``: Restrict processing of the directive to command line ``-o`` options
* ``parameters``: Restrict processing of the directive to certain parameter names and values

Examples
--------

Explicitly disable a test

.. code-block:: python

   import nvtest
   nvtest.directives.enable(False)

.. code-block:: python

   #VVT: enable : false

----

Enable the test if the platform name is not "ATS"

.. code-block:: python

   import nvtest
   nvtest.directives.enable(True, platforms="not ATS")

.. code-block:: python

   #VVT: enable (platform="not ATS") : true

----

More examples:

.. code-block:: python

   import nvtest
   nvtest.directives.enable(True, testname="foo", platform="Darwin or Linux")
   nvtest.directives.enable(True, platform="not Windows", options="not debug")
   nvtest.directives.enable(False, testname="foo")

.. code-block:: python

   #VVT: enable (testname=foo, platform="Darwin or Linux") : true
   #VVT: enable (platform="not Windows", options="not debug") : true
   #VVT: enable (testname=foo) : false
