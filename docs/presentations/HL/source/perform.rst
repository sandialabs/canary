How does Canary perform?
------------------------

Test case: CPU build of Trilinos

.. revealjs-fragments::

    * Tpetra stack (Tpetra, MueLu, Belos)
    * 1255 CMake (CTest) tests
    * Run on commodity hardware

.. revealjs-break::
   :data-transition: none

.. container:: fragment

    .. code-block:: console

        $ ctest -j16
        100% tests passed, 0 tests failed out of 1255
        ...
        Total Test time (real) = 164.17 sec

.. container:: fragment

    .. code-block:: console

        $ canary run -w --workers=16 .
        ...
        INFO: 1250/1250 tests finished with status PASS
        INFO: Finished session in 125.73 s. with returncode 0

.. container:: fragment

    For this simple use-case, ``ctest`` and ``canary`` are in the same ballpark.

.. revealjs-break::
   :data-transition: none

What if I want to run the tests in a slurm queue?


.. container:: fragment

    .. code-block:: console

        $ canary hpc run -w --scheduler slurm --batch-count=40 --workers=40 .
        ...
        INFO: 1250/1250 tests finished with status PASS
        INFO: Finished session in 44.86 s. with returncode 0

.. revealjs-fragments::

   * Canary eliminates writing submission scripts; and
   * allows submitting tests across multiple nodes, in a single shot.


.. revealjs-break::
   :data-transition: none

What if I have a pool of machines to work with (common on Sandia's Build and Test Farm)?

.. container:: fragment

    .. code-block:: console

        $ canary dist run -w --server HOST:PATH --batch-count=40 --workers=40 .
        ...
        INFO: 1250/1250 tests finished with status PASS
        INFO: Finished session in 64.86 s. with returncode 0


.. revealjs-break::
   :data-transition: none

.. image:: _static/compvvtest.png
   :width: 60%
