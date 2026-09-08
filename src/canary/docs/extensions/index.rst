.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extensions:

Extensions
==========

``canary`` is extended through plugins that register under the ``canary``
entry point group.  This section documents the bundled extensions and explains
how to author new ones.

.. toctree::
   :maxdepth: 1

   authoring

.. rubric:: Installed extensions

The pages below are generated at build time from every installed ``canary``
plugin that ships a ``docs/`` folder.  If no extensions are found the section
below will be empty.

.. toctree::
   :maxdepth: 1
   :glob:

   exts/*/index
