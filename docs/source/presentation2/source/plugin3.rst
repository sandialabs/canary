Other plugins
-------------

Nearly every stage of Canary execution is customizable by implementing a plugin hook.

.. revealjs-break::

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
        mpi("-n", str(job.parameters.cpus), env=env)

.. revealjs-fragments::

    * But now this test is specific to nvidia
    * Is there a better way?


canary_nvidia
^^^^^^^^^^^^^

.. code-block:: python

    @canary.hookimpl
    def canary_gpu_backend_detect(config: canary.Config) -> str | None:
        return "nvidia" if shutil.which("nvidia-smi") else None


    @canary.hookimpl
    def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
        return _nvidia_smi_list_gpus(config)


    @canary.hookimpl
    def canary_runteststart(case: canary.TestCase):
        gpu_ids = [id for id in case.gpu_ids if id.startswith("NVIDIA:")]
        if gpu_ids:
            visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
            case.variables["CUDA_VISIBLE_DEVICES"] = visible

.. revealjs-break::

Test cases need only parameterize over ``gpus`` and the plugin will detect GPU resources and define the correct visible devices variable.

.. code-block:: python

    import os
    import canary
    canary.directives.parameterize("cpus,gpus", [(1, 1), (4, 4)])

    def test():
        job = canary.get_instance()
        mpi = canary.Executable("mpiexec")
        mpi("-n", str(job.parameters.cpus))

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

   * - ``canary_addhooks``
     - Add/extend hook specifications at plugin registration.
   * - ``canary_addoption``
     - Register command-line options.
   * - ``canary_addcommand``
     - Register a Canary subcommand.
   * - ``canary_configure``
     - Plugin configuration after option parsing.
   * - ``canary_sessionstart``
     - Session start callback.
   * - ``canary_sessionfinish``
     - Session finish callback.
   * - ``canary_collectstart``
     - Start collection; add generators/skip dirs.
   * - ``canary_collect_modifyitems``
     - Filter/reorder collected items.
   * - ``canary_collect_report``
     - Report collection results.
   * - ``canary_testcase_generator``
     - Select a testcase generator implementation.
   * - ``canary_generatestart``
     - Start test generation.
   * - ``canary_generate_modifyitems``
     - Modify generated items.
   * - ``canary_generate_report``
     - Report generation results.

.. revealjs-break::

.. list-table::
   :widths: 35 65
   :class: smalltable

   * - ``canary_selectstart``
     - Start selection.
   * - ``canary_select_modifyitems``
     - Modify selected items.
   * - ``canary_select_report``
     - Report selection results.
   * - ``canary_rtselectstart``
     - Start runtime selection.
   * - ``canary_rtselect_modifyitems``
     - Modify runtime-selected items.
   * - ``canary_rtselect_report``
     - Report runtime selection results.
   * - ``canary_runtests_start``
     - Begin ``canary run`` (pre-run hook).
   * - ``canary_runtests``
     - Run tests (main run hook).
   * - ``canary_runtests_report``
     - Report run results.
   * - ``canary_runtest_launcher``
     - Provide the launcher for a testcase.
   * - ``canary_runteststart``
     - Setup phase for a testcase.
   * - ``canary_runtest``
     - Execute a testcase.
   * - ``canary_runtest_finish``
     - Finish/postprocess a testcase.

.. revealjs-break::

.. list-table::
   :widths: 35 65
   :class: smalltable

   * - ``canary_resource_pool_fill``
     - Populate the resource pool.
   * - ``canary_resource_pool_accommodates``
     - Decide if a testcase can run (resource check).
   * - ``canary_resource_pool_count``
     - Count available resources of a type.
   * - ``canary_resource_pool_count_per_node``
     - Count available resources per node.
   * - ``canary_resource_pool_types``
     - List available resource types.
   * - ``canary_resource_pool_describe``
     - Describe the resource pool (human-readable).
