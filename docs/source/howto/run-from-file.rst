.. _how-to-from-file:

How to run specific tests from a file
=====================================

Select tests can be executed by specifying their paths in a ``json`` or ``yaml`` configuration file with the following schema:

.. code-block:: yaml

    testpaths:
    - ROOT: str
      PATHS:
      - str

where ``ROOT`` is a parent directory of the tests and ``PATHS`` are the file paths relative to ``ROOT``.  Consider, for example the following directory tree:

.. code-block:: console

   $ tree tests
   tests/
   └── regression
       └── 2D
           ├── test_1.pyt
           └── test_2.pyt
   └── verification
       └── 2D
           ├── test_1.pyt
           └── test_2.pyt
       └── 3D
           ├── test_1.pyt
           └── test_2.pyt
   └── prototype
       └── a
           ├── test_1.pyt
           └── test_2.pyt
       └── b
           ├── test_1.pyt
           └── test_2.pyt

To run only ``regression/2D/test_1.pyt``, ``verification/3D/test_2.pyt``, and ``prototype/b/test_1.pyt``, write the following to ``tests.json``

.. code-block:: json

    {
      "testpaths": [
        {
          "tests": [
            "regression/2D/test_1.pyt",
            "verification/3D/test_2.pyt",
            "prototype/b/test_1.pyt"
          ]
        }
      ]
    }

and pass it to ``nvtest run``:

.. code-block:: console

    nvtest run tests.json
