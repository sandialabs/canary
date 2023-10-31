timeout
=======

Specify a timeout value for a test

.. code-block:: python

   timeout(arg, options=None, platforms=None, parameters=None, testname=None)

.. code-block:: python

   # VVT: timeout (options=..., platforms=..., parameters=..., testname=...) : arg

Parameters
----------

* ``arg``: The time in seconds.  Natural language forms such as "20m", "1h 20m", and HH:MM:SS such as "2:30:00" are also allowed and converted to seconds.
* ``testname``: Restrict processing of the directive to this test name
* ``platforms``: Restrict processing of the directive to certain platform or platforms
* ``options``: Restrict processing of the directive to command line ``-o`` options
* ``parameters``: Restrict processing of the directive to certain parameter names and values
