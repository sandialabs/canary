Really, everything is a plugin
------------------------------

.. container:: fragment

   .. code-block:: python

      @canary.hookspec(first_result=True)
      def canary_runtests(cases: list[TestCase]) -> bool: ...

.. container:: fragment

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

.. revealjs-break::
    :data-transition: none

.. code-block:: python

   @canary.hookspec(first_result=True)
   def canary_runtests(cases: list[TestCase]) -> bool: ...

.. container:: fragment

    .. code-block:: python
        :linenos:
        :emphasize-lines: 4-7

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
            with ResourceQueueExecutor(queue, ...) as ex:
                ex.run(backend=self.backend.name)
            return True

.. revealjs-break::
    :data-transition: none

.. code-block:: python

   @canary.hookspec(first_result=True)
   def canary_runtests(cases: list[TestCase]) -> bool: ...

.. container:: fragment

    .. code-block:: python
        :linenos:
        :emphasize-lines: 8

        @canary.hookimpl(tryfirst=True)
        def canary_runtests(cases: list[TestCase]) -> bool:
            """Run test cases in batches on distributed pool of machines"""
            batches = []
            for batched in batch_testcases(cases=cases, ...):
                batch = TestBatch(batched, ...)
                batches.append(batch)
            dpool = DistributedResourcePool(...)
            queue = ResourceQueue(dpool)
            queue.put(*batches)
            queue.prepare()
            with ResourceQueueExecutor(queue, ...) as ex:
                ex.run(backend=self.backend.name)
            return True
