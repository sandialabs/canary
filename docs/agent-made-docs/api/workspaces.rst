.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _api-workspaces:

Workspace API
=============

Workspace and session management APIs.

Workspace Management
--------------------

.. autoclass:: _canary.workspace.workspace.Workspace
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

.. autoclass:: _canary.workspace.session.Session
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Execution Space
---------------

.. autoclass:: _canary.core.execspace.ExecutionSpace
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

Persistence
-----------

.. autoclass:: _canary.persistence.database.WorkspaceDatabase
   :members:
   :member-order: bysource
   :undoc-members:
   :show-inheritance:

   .. note::
      This class is primarily persistence infrastructure and is included for
      completeness. Most extension authors will interact with the higher-level
      :py:class:`_canary.workspace.workspace.Workspace` and :py:class:`_canary.workspace.session.Session` APIs.

See Also
--------

- :doc:`../user/workspaces`: Workspace concepts
- :doc:`../user/sessions`: Session concepts