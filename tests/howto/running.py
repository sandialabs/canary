"""
How to run tests
================

Basic usage
-----------

.. code-block:: console

   nvtest run PATH

Filter tests to run by keyword
------------------------------

.. code-block:: console

   nvtest run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression.  For example, ``-k 'key1 and not key2``.

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   nvtest run --max-workers=N PATH [PATHS...]

Set a timeout on the test session
---------------------------------

.. code-block:: console

   nvtest run --timeout=TIME_EXPR PATH [PATHS...]

where ``TIME_EXPR`` is a number or a human-readable number representation like ``1 sec``, ``1s``, etc.

Run tests in a batch scheduler
------------------------------

Basic usage
^^^^^^^^^^^

.. code-block:: console

   nvtest run [--batches=N|--batch-size=T] [OPTIONS] PATH [PATHS...]

Use slurm scheduler
^^^^^^^^^^^^^^^^^^^

.. code-block:: console

   nvtest run --runner=slurm PATH [PATHS...]

Pass arguments to the scheduler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

   nvtest run --runner=slurm -R,ARG1 -R,ARG2 PATH [PATHS...]

where ``ARGI`` are passed directly to the scheduler.  Eg, ``-R,--account=XXYYZZ01``
"""

import os

from _nvtest.util.filesystem import working_dir


def test_run(tmpdir):
    from _nvtest.main import NVTestCommand

    run = NVTestCommand("run")
    with working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.keywords('a', 'b')\n")
            fh.write("def test():\n    return 0\ntest()\n")
        run("-d", "Foo", ".")
        assert os.path.exists("Foo")
        assert os.path.exists("Foo/.nvtest/config")
        assert os.path.exists("Foo/test")
