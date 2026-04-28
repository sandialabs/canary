Really, everything is a plugin
------------------------------

.. code-block:: python

   @canary.hookspec
   def canary_runtests(cases: list[TestCase]) -> bool: ...


.. revealjs-break::

.. code-block:: python

   @canary.hookimpl(trylast=True)
   def canary_runtests(cases: list[TestCase]) -> bool:
       """Default implementation"""
       queue = ResourceQueue(...)
       queue.put(*cases)
       queue.prepare()
       with ResourceQueueExecutor(queue, ...) as ex:
           ex.run()
       return True

.. revealjs-fragments::

  ``TestCase.run`` executes the test script.


.. revealjs-break::

The ``canary-hpc`` plugin defines:

.. code-block:: python

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(cases: list[TestCase]) -> bool:
        """Run test cases in batches on HPC systems"""
        batches = []
        for batched in batch_testcases(cases=cases, ...):
            batch = TestBatch(batched, ...)
            batches.append(batch)
        queue = ResourceQueue(...)
        queue.put(*batches)
        queue.prepare()
        executor = BatchExecutor()
        with ResourceQueueExecutor(queue, ...) as ex:
            ex.run(backend=self.backend.name)
        return True

.. revealjs-fragments::

  ``TestBatch.run`` runs the test cases in the batch in the HPC scheduler (slurm, pbs, flux, etc.)


.. revealjs-break::

The ``canary-dist`` plugin defines:

.. code-block:: python

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(cases: list[TestCase]) -> bool:
        """Run test cases in batches on HPC systems"""
        batches = []
        for batched in batch_testcases(cases=cases, ...):
            batch = TestBatch(batched, ...)
            batches.append(batch)
        queue = ResourceQueue(...)
        queue.put(*batches)
        queue.prepare()
        executor = BatchExecutor()
        dpool = DistributedResourcePool(...)
        with ResourceQueueExecutor(queue, dpool, ...) as ex:
            ex.run(backend=self.backend.name)
        return True

.. revealjs-fragments::

  ``DistributedResourcePool`` defines a pool of resources shared between machines.
