.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _api-workspaces:

Workspace API
=============

Workspace and session management APIs.

Workspace Management
--------------------

.. autoclass:: _canary.workspace.Workspace
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.workspace.Session
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Execution Space
---------------

.. autoclass:: _canary.testexec.ExecutionSpace
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Persistence
-----------

.. autoclass:: _canary.database.WorkspaceDatabase
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

   .. note::
      This class is primarily persistence infrastructure and is included for
      completeness. Most extension authors will interact with the higher-level
      :py:class:`_canary.workspace.Workspace` and :py:class:`_canary.workspace.Session` APIs.

See Also
--------

- :doc:`../user/workspaces`: Workspace concepts
- :doc:`../user/sessions`: Session concepts