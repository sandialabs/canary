Canary is
---------

.. revealjs-fragments::

  * an asynchronous job execution tool;
  * fast, scalable, and portable from laptops to HPC;
  * designed for **testing** scientific applications;
  * but, well suited for engineering workflows; and
  * installable today::

      pip install canary-wm


Typical usage
^^^^^^^^^^^^^

.. mermaid::

   %%{init: {
     'theme': 'dark',
     'themeVariables': { 'nodeTextAlignment': 'center' }
   } }%%

   flowchart TB
        C($ canary run PATHS) --> E(Scan PATHS for test generators)
        E --> G(Generate test cases)
        G --> I(Run tests cases asynchronously)
        I --> J(Report results)
