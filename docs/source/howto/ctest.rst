.. _howto-ctest:

Run CTest tests
===============

In addition to :ref:`CMake integration<howto-cmake-integration>`, ``nvtest`` can run `CTest <https://cmake.org/cmake/help/latest/manual/ctest.1.html>`_ tests natively.  Simply pass the path to a CMake build directory containing CTest tests:

.. code-block:: console

    $ nvtest run CMAKE_BINARY_DIR

``nvtest`` will read the CTest instructions and write a ``.pyt`` test file for each test added by ``add_test``.
