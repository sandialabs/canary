``ResourceQueueExecutor``
-------------------------

The execution engine

.. code-block:: text

   start N persistent workers

   while ResourceQueue not empty:
       (job, resources) = ResourceQueue.checkout()
       worker = next idle worker
       worker.run_in_new_process(job)
       ResourceQueue.checkin(job, resources)
