.. _configuration-env:

Setting configuration variables in your environment
===================================================

Configuration settings can be set via environment variable by naming the variable ``NVTEST_<SECTION>_<NAME>=<VALUE>``, where ``SECTION`` is a configuration section and ``NAME`` is the configuration variable name.  Eg,

.. code-block:: console

   export NVTEST_LOG_LEVEL=DEBUG

.. note::

   Configuration settings set in the environment take precedence over configuration settings set in a file.
