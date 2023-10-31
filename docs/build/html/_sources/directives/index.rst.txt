Test Directives
===============

Before running a test, ``nvtest`` reads the test file looking for "test directives".   Test directives are instructions for how to setup and allocate resources needed by the test.  The ``.pyt`` and ``.vvt`` file types use different directive styles.  In the ``.pyt`` file type, directives are python commands contained in the ``nvtest.mark`` namespace.  In the ``.vvt`` file type, text directives are preceded with ``#VVT:`` and ``nvtest`` will stop processing further ``#VVT:`` directives once the first non-comment non-whitespace line has been reached in the test script.

The general format for a directive is

``.pyt``:

.. code-block:: python

   import nvtest
   nvtest.mark.directive_name(*args, **kwargs)

``.vvt``:

.. code-block:: python

    #VVT: directive_name [(kwd=val[, ...])] [: args]

``.vvt`` directives can be continued on subsequent lines by starting them with ``#VVT::``:

.. code-block:: python

    #VVT: directive_name : args
    #VVT:: ...
    #VVT:: ...

Which is equivalent to

.. code-block:: python

    #VVT: directive_name : args ... ...

.. raw:: html

   <font size="+3"> Available test directives:</font>

.. toctree::
   :maxdepth: 1

   analyze
   copy
   enable
   keywords
   link
   parameterize
   skipif
   testname
   timeout
