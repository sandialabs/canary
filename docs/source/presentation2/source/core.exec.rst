``ResourceQueueExecutor``
-------------------------

The execution engine

.. revealjs-fragments::

   * Starts ``n`` **persistent workers**

     * Workers stay alive across many jobs
     * Lower overhead, better throughput

   * Each job runs in its **own process**

     * Timeouts enforceable
     * Crashes contained
     * Consistent environment

.. revealjs-break::
    :notitle:

.. mermaid::

   %%{init: {'theme': 'dark', 'themeVariables': {'primaryTextColor': '#ffffff', 'lineColor': '#ffffff'}, 'sequence': {'mirrorActors': false}} }%%

   sequenceDiagram
     participant Q as ResourceQueue
     participant P as ResourcePool
     participant X as ResourceQueueExecutor
     participant W as Worker
     participant J as Job process

     Q->>P: checkout(requested resources)
     P-->>Q: allocation (ids + slots)
     Q-->>X: runnable job + allocation
     X->>W: dispatch(job)
     W->>J: spawn per-job process
     J-->>W: events (STARTED/FINISHED)
     W-->>X: job finished
     X-->>Q: done(job)
     Q->>P: checkin(allocation)

.. revealjs-break::
    :notitle:

.. mermaid::

   %%{init: {'theme': 'dark'} }%%

   flowchart TB
        A(User) --> C($ canary run PATHS)
        C --> E(Scan PATHS for\ntest generators)
        E --> G(Generate test cases)
        G --> I(Run tests cases\nasynchronously)
        I --> J(Report results)
