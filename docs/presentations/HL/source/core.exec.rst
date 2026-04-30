``ResourceQueueExecutor``
-------------------------

The execution engine

.. code-block:: python

   workers = start_persistent_workers(N)
   while True:
       poll_worker_events()
       for (worker, job) in completed_jobs():
           queue.done(job)
           workers.append(worker)
       if queue.empty() and not inflight_jobs():
           break
       if not workers:
           continue
       try:
           job = queue.get()
       except Empty:
           continue
       worker = workers.pop()
       worker.submit(job)
       mark_inflight(worker, job)
