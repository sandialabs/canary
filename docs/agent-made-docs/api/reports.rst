.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _api-reports:

Report API
==========

Reporting and reporter extension APIs.

Reporter Base Classes
---------------------

.. autoclass:: _canary.reporter.Reporter
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.reporter.LiveReporter
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.reporter.EventReporter
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Reporter Protocols
------------------

.. autoclass:: _canary.reporter.ReporterQueueProtocol
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.reporter.ReporterExecutorProtocol
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

See Also
--------

- :doc:`../extending/reporters`: Reporter development