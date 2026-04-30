Core components
---------------

Pulling it together

.. mermaid::

   %%{init: {'theme': 'dark'} }%%
   sequenceDiagram
     participant Exec as ResourceQueueExecutor
     participant Q as ResourceQueue
     participant Pool as ResourcePool
     participant W as Worker processes
     participant P as Job process

     Exec->>W: start N worker processes
     loop until queue empty
       Exec->>Q: get next job
       Q->>Pool: checkout resources
       Q-->>Exec: job
       Exec->>W: dispatch job
       W->>P: run job
       P-->>Exec: complete
       Exec-->>Q: done
       Q->>Pool: checkin resources
     end
