How does Canary perform?
------------------------

.. revealjs-fragments::

    * Test case: CPU build of Trilinos
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

        $ canary run --workers=16 .
        ...
        INFO: 1250/1250 tests finished with status PASS
        INFO: Finished session in 125.73 s. with returncode 0

.. container:: fragment

   .. raw:: html

       <div class="callout-box style="position: absolute; bottom: -2rem; left: 0rem; font-size: 18px; opacity: 0.8;">
        Canary filtered 5 additional cases due to resource constraints
       </div>

.. revealjs-break::
   :data-transition: none

.. code-block:: console

    $ ctest -j16
    100% tests passed, 0 tests failed out of 1255
    ...
    Total Test time (real) = 164.17 sec

.. code-block:: console

    $ canary run --workers=16 .
    ...
    INFO: 1250/1250 tests finished with status PASS
    INFO: Finished session in 125.73 s. with returncode 0

.. revealjs-fragments::

   * ``ctest`` and ``canary`` performance is comparable
   * Runtime is dominated by test execution

What if I want to run tests in a slurm queue?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. container:: fragment

    .. code-block:: console

        $ cat ctest.batch
        #!/usr/bin/sh
        # SBATCH: ...
        ctest -j16
        $ sbatch ctest.batch

.. container:: fragment

    .. code-block:: console

        $ canary hpc run \
          -b backend=slurm -b options=... -b workers=16

.. revealjs-fragments::

   * Canary eliminates writing submission scripts
   * Otherwise the workflow is similar (you still pass scheduler options, e.g., sbatch args)

What if I want to run tests on many compute nodes?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. container:: fragment

    .. code-block:: console

        $ canary hpc run \
          -b backend=slurm -b options=... -b workers=16 \
          -b spec=count:40 --workers=40

.. revealjs-fragments::

   * ``canary-hpc``: batch test cases and fan them across multiple **compute nodes**


What if I want to run tests across a build/test farm?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. container:: fragment

    .. code-block:: console

        $ canary dist run \
          -b spec=count:40 --workers=40 \
          --server HOST:PATH

.. revealjs-fragments::

   * ``canary-dist``: batch test cases and fan them across multiple **machines**

Performance comparison
^^^^^^^^^^^^^^^^^^^^^^

.. image:: _static/compvvtest.pdf
   :width: 60%

How does Canary perform?
^^^^^^^^^^^^^^^^^^^^^^^^

.. revealjs-fragments::

  * Overall runtime is driven primarily by test execution, not runner overhead.
  * Canary adds value by enabling:

    .. revealjs-fragments::

      * Flexible execution across multiple test formats
      * Extension via a plugin framework
      * Less boilerplate when building complex, multi-machine workflows
