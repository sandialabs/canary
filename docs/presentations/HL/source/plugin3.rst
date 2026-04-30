Other plugins
-------------

Nearly every stage of Canary execution is customizable by implementing a plugin hook.

.. revealjs-break::
   :data-transition: none

Consider the test

.. code-block:: python

    import os
    import canary
    canary.directives.parameterize("cpus,gpus", [(1, 1), (4, 4)])

    def test():
        job = canary.get_instance()
        mpi = canary.Executable("mpiexec")
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = ",".join(job.gpu_ids)
        mpi("-n", str(job.cpus), "my-program", env=env)

.. revealjs-fragments::

    * Every test must define CUDA_VISIBLE_DEVICES
    * Is there a better way?


canary_runteststart
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    @canary.hookimpl
    def canary_runteststart(case: canary.TestCase):
        case.variables["CUDA_VISIBLE_DEVICES"] = ",".join(case.gpu_ids)

.. container:: fragment

  .. code-block:: python

      import os
      import canary
      canary.directives.parameterize("cpus,gpus", [(1, 1), (4, 4)])

      def test():
          job = canary.get_instance()
          mpi = canary.Executable("mpiexec")
          mpi("-n", str(job.cpus), "my-program")


.. container:: fragment

   But what if we want the test to work for both ``cpu`` and ``gpu`` builds of an application?

.. revealjs-break::
   :data-transition: none

.. code-block:: python

    @canary.hookimpl
    def canary_runteststart(case: canary.TestCase):
        if case.gpu_ids:
            case.variables["CUDA_VISIBLE_DEVICES"] = ",".join(case.gpu_ids)

.. code-block:: python

    import os
    import canary
    canary.directives.parameterize("cpus", [1, 4], when="options='not gpu'")
    canary.directives.parameterize("cpus,gpus", [(1, 1), (4, 4)], when="options=gpu")

    def test():
        job = canary.get_instance()
        mpi = canary.Executable("mpiexec")
        mpi("-n", str(job.cpus), "my-program")

.. container:: fragment

   .. code-block:: console

     $ canary run ...   # Run CPU-only parameterization
     $ canary run -o gpu ...   # Run GPU parameterization


canary_nvidia
^^^^^^^^^^^^^

.. code-block:: python

    @canary.hookimpl
    def canary_gpu_backend_detect(config: canary.Config) -> str | None:
        return "nvidia" if shutil.which("nvidia-smi") else None


.. code-block:: python

    @canary.hookimpl
    def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
        return _nvidia_smi_list_gpus(config)


.. code-block:: python

    @canary.hookimpl
    def canary_runteststart(case: canary.TestCase):
        gpu_ids = [id for id in case.gpu_ids if id.startswith("NVIDIA:")]
        if gpu_ids:
            visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
            case.variables["CUDA_VISIBLE_DEVICES"] = visible


Builtin plugins
^^^^^^^^^^^^^^^

.. list-table::
   :widths: 40 60
   :class: smalltable

   * - ``canary_hpc``
     - Run tests on HPC systems
   * - ``canary_dist``
     - Run tests on a distributed pool of machines
   * - ``canary_nvidia``
     - Detect nvidia gpus and set ``CUDA_VISIBLE_DEVICES``
   * - ``canary_amd``
     - Detect AMD gpus and set ``ROCM_VISIBLE_DEVICES``
   * - ``canary_notebook``
     - Run Jupyter notebooks as tests
   * - ``canary_gitlab``
     - Interact with GitLab API
   * - ``canary_cmake``
     - Run CMake generated tests
   * - ``canary_cdash``
     - Post test results to CDash

Plugin specs
^^^^^^^^^^^^

.. list-table::
   :widths: 35 65
   :class: smalltable

   * - :py:`canary_addhooks`
     - Add/extend hook specifications at plugin registration.
   * - :py:`canary_addoption`
     - Register command-line options.
   * - :py:`canary_addcommand`
     - Register a Canary subcommand.
   * - :py:`canary_configure`
     - Plugin configuration after option parsing.
   * - :py:`canary_sessionstart`
     - Session start callback.
   * - :py:`canary_sessionfinish`
     - Session finish callback.
   * - :py:`canary_collectstart`
     - Start collection; add generators/skip dirs.
   * - :py:`canary_collect_modifyitems`
     - Filter/reorder collected items.
   * - :py:`canary_collect_report`
     - Report collection results.
   * - :py:`canary_testcase_generator`
     - Select a testcase generator implementation.
   * - :py:`canary_generatestart`
     - Start test generation.
   * - :py:`canary_generate_modifyitems`
     - Modify generated items.
   * - :py:`canary_generate_report`
     - Report generation results.

.. revealjs-break::
   :data-transition: none

.. list-table::
   :widths: 35 65
   :class: smalltable

   * - :py:`canary_selectstart`
     - Start selection.
   * - :py:`canary_select_modifyitems`
     - Modify selected items.
   * - :py:`canary_select_report`
     - Report selection results.
   * - :py:`canary_rtselectstart`
     - Start runtime selection.
   * - :py:`canary_rtselect_modifyitems`
     - Modify runtime-selected items.
   * - :py:`canary_rtselect_report`
     - Report runtime selection results.
   * - :py:`canary_runtests_start`
     - Begin :py:`canary run` (pre-run hook).
   * - :py:`canary_runtests`
     - Run tests (main run hook).
   * - :py:`canary_runtests_report`
     - Report run results.
   * - :py:`canary_runtest_launcher`
     - Provide the launcher for a testcase.
   * - :py:`canary_runteststart`
     - Setup phase for a testcase.
   * - :py:`canary_runtest`
     - Execute a testcase.
   * - :py:`canary_runtest_finish`
     - Finish/postprocess a testcase.

.. revealjs-break::
   :data-transition: none

.. list-table::
   :widths: 35 65
   :class: smalltable

   * - :py:`canary_resource_pool_fill`
     - Populate the resource pool.
   * - :py:`canary_resource_pool_accommodates`
     - Decide if a testcase can run (resource check).
   * - :py:`canary_resource_pool_count`
     - Count available resources of a type.
   * - :py:`canary_resource_pool_count_per_node`
     - Count available resources per node.
   * - :py:`canary_resource_pool_types`
     - List available resource types.
   * - :py:`canary_resource_pool_describe`
     - Describe the resource pool (human-readable).
