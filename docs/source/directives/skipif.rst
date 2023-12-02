.. _directive-skipif:

skipif
======

Conditionally skip tests

.. code:: python

   skipif(arg, *, reason)

.. code:: python

   #VVT: skipif : python_expression

Parameters
----------

* ``arg``: If ``True``, the test will be skipped.
* ``python_expression``: String that is evaluated and cast to a ``bool``. If the result is ``True`` the test will be skipped.
* ``reason``: The reason the test is being skipped.

Examples
--------

.. code:: python

   import sys
   import nvtest
   nvtest.directives.skipif(sys.platform == "Darwin", reason="Test does not run on Apple hardware")

.. code:: python

   #VVT: skipif (reason=Test does not run on Apple hardware) : sys.platform == "Darwin"

will skip the test if run on Apple hardware.

If ``reason`` is not defined, ``nvtest`` reports the reason as ``"python_expression evaluated to True"``.

Checking module availability
----------------------------

A test may be skipped if a module is not importable by using the ``importable`` function. ``importable(module_name)`` evaluates to ``True`` if ``module_name`` can be imported otherwise, ``False``. For example,

.. code-block:: python

   #VVT: skipif : not importable("numpy")

would skip the test if ``numpy`` was not available.

Evaluation namespace
--------------------

``python_expression`` is evaluated in a minimal namespace consisting of the ``os`` module, ``sys`` module, and ``importable`` function.
