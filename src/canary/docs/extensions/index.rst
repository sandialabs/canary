.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extensions:

Extensions
==========

``canary`` is extended through plugins that register under the ``canary``
entry point group.  This section documents the bundled extensions and explains
how to author new ones.

If you are trying to accomplish a user task such as running CTest tests,
submitting work through an HPC scheduler, or running existing ``.vvt`` suites,
start with the task-oriented pages in the :doc:`/user/index`. Use the extension
pages here when you want deeper implementation detail, extension-specific
behavior, or authoring guidance.

.. toctree::
   :maxdepth: 1

   authoring

.. toctree::
   :maxdepth: 1
   :caption: In-depth guides

   plugins
   hooks
   configuration
   resources
   measurements
   generators
   commands
   reporters
   docs

.. rubric:: Installed extensions

The pages below are generated at build time from every installed ``canary``
plugin that ships a ``docs/`` folder.  If no extensions are found the section
below will be empty.

.. toctree::
   :maxdepth: 1
   :glob:

   exts/*/index
