.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _api-jobs:

Job API
=======

Job specification and execution APIs.

Job Specification IR
--------------------

.. autoclass:: _canary.ir.JobSpecIR
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.ir.DependencySelector
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Job Specification
-----------------

.. autoclass:: _canary.jobspec.JobSpec
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.jobspec.SpecDependency
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.jobspec.Asset
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.jobspec.Artifact
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.jobspec.Mask
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Job Execution
-------------

.. autoclass:: _canary.job.Job
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.job.JobState
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.job.JobPhase
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.job.Dependency
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.job.Measurements
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Timekeeping
-----------

.. autoclass:: _canary.timekeeper.Timekeeper
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

See Also
--------

- :doc:`../user/jobs`: Job concepts
- :doc:`../extending/generators`: Generator development